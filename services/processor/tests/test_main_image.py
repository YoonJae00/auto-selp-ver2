import os
import sys
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image, ImageChops, ImageDraw

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "internal-test-token")
for key in (
    "NAVER_API_KEY",
    "NAVER_SECRET_KEY",
    "NAVER_CUSTOMER_ID",
    "NAVER_CLIENT_ID",
    "NAVER_CLIENT_SECRET",
    "Coupang_Access_Key",
    "Coupang_Secret_Key",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
):
    os.environ.setdefault(key, "test")

import main
import tasks
from schemas import MainImageProcessRequest
from schemas import ProductResponse
from utils import main_image


def image_bytes(image: Image.Image, image_format: str = "PNG") -> bytes:
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_rembg_session_uses_isnet_general_and_is_cached(monkeypatch):
    new_session = Mock(return_value=object())
    monkeypatch.setitem(sys.modules, "rembg", SimpleNamespace(new_session=new_session))
    main_image.get_rembg_session.cache_clear()
    try:
        first = main_image.get_rembg_session()
        second = main_image.get_rembg_session()
    finally:
        main_image.get_rembg_session.cache_clear()

    assert first is second
    new_session.assert_called_once_with("isnet-general-use")


def test_process_main_image_is_deterministic_and_preserves_foreground_aspect(monkeypatch):
    source = Image.new("RGB", (800, 600), "white")
    segmented = Image.new("RGBA", source.size, (0, 0, 0, 0))
    ImageDraw.Draw(segmented).rectangle((200, 200, 599, 399), fill=(230, 15, 20, 255))
    monkeypatch.setattr(main_image, "_remove_background", lambda _: image_bytes(segmented))
    product_id = uuid.uuid4()

    first = main_image.process_main_image(image_bytes(source), product_id)
    second = main_image.process_main_image(image_bytes(source), product_id)
    output = Image.open(BytesIO(first))

    assert ImageChops.difference(output, Image.open(BytesIO(second))).getbbox() is None
    assert output.size == (1000, 1000)
    assert output.mode == "RGB"
    red, green, blue = output.split()
    foreground_mask = ImageChops.multiply(
        red.point(lambda value: 255 if value > 170 else 0),
        ImageChops.multiply(
            green.point(lambda value: 255 if value < 90 else 0),
            blue.point(lambda value: 255 if value < 90 else 0),
        ),
    )
    bbox = foreground_mask.getbbox()
    assert bbox is not None
    width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    assert 1.9 < width / height < 2.1


def test_process_main_image_rejects_invalid_foreground_ratio(monkeypatch):
    source = Image.new("RGB", (600, 600), "white")
    segmented = Image.new("RGBA", source.size, (10, 20, 30, 255))
    monkeypatch.setattr(main_image, "_remove_background", lambda _: image_bytes(segmented))

    with pytest.raises(ValueError, match="5%-95%"):
        main_image.process_main_image(image_bytes(source), uuid.uuid4())


@pytest.mark.anyio
async def test_private_image_url_is_rejected():
    with pytest.raises(ValueError, match="non-public"):
        await main_image._validate_public_url("http://127.0.0.1/image.jpg")


class ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.added = []
        self.statements = []
        self.commits = 0

    async def execute(self, statement):
        self.statements.append(statement)
        return ScalarRows(self.rows)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


def test_main_image_endpoint_requires_authentication(monkeypatch):
    monkeypatch.setattr(main, "seed_prompts", AsyncMock())
    main.app.dependency_overrides[main.get_db] = lambda: FakeDB([])
    try:
        with TestClient(main.app) as client:
            response = client.post(
                "/products/process-main-images",
                json={"product_ids": [str(uuid.uuid4())]},
            )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 401


def product(product_id, user_id, *, status="completed", images=None):
    return SimpleNamespace(
        id=product_id,
        user_id=user_id,
        original_name=str(product_id),
        status=status,
        images_list=images if images is not None else ["https://img.example/main.jpg"],
        image_processing_status="not_started",
        processed_image_path=None,
        warnings=None,
        updated_at=datetime(2026, 7, 23),
    )


def test_product_response_only_emits_existing_processed_image_url(monkeypatch, tmp_path):
    monkeypatch.setattr(main_image, "PROCESSED_IMAGE_ROOT", tmp_path)
    item = product(uuid.uuid4(), uuid.uuid4())
    item.image_processing_status = "completed"
    target = main_image.processed_image_path(item.user_id, item.id)
    item.processed_image_path = str(target)
    item.created_at = item.updated_at
    item.platform_mappings = []
    response = ProductResponse.model_validate(item)

    missing = response.model_dump()
    assert missing["processed_main_image_url"] is None
    assert "processed_image_path" not in missing
    assert "user_id" not in missing

    target.parent.mkdir(parents=True)
    target.write_bytes(b"jpeg")
    existing = response.model_dump()
    assert existing["processed_main_image_url"].startswith(
        f"/api/processor/products/{item.id}/processed-main-image?v="
    )
    assert "processed_image_path" not in existing


class SingleResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class SingleDB:
    def __init__(self, value):
        self.value = value

    async def execute(self, _):
        return SingleResult(self.value)


@pytest.mark.anyio
async def test_processed_image_get_requires_owned_product_and_existing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(main_image, "PROCESSED_IMAGE_ROOT", tmp_path)
    user_id = uuid.uuid4()
    item = product(uuid.uuid4(), user_id)
    item.image_processing_status = "completed"
    target = main_image.processed_image_path(user_id, item.id)
    item.processed_image_path = str(target)

    for db in (SingleDB(None), SingleDB(item)):
        with pytest.raises(HTTPException) as error:
            await main.get_processed_main_image(item.id, {"id": user_id}, db)
        assert error.value.status_code == 404

    target.parent.mkdir(parents=True)
    target.write_bytes(b"jpeg")
    response = await main.get_processed_main_image(item.id, {"id": user_id}, SingleDB(item))
    assert Path(response.path) == target


@pytest.mark.anyio
async def test_start_main_image_processing_validates_ownership_and_eligibility(monkeypatch):
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    request = MainImageProcessRequest(product_ids=[product_id])
    queued = SimpleNamespace(id="image-task")
    apply_async = lambda **kwargs: queued
    monkeypatch.setattr(main.process_main_images_task, "apply_async", apply_async)

    db = FakeDB([product(product_id, user_id)])
    response = await main.start_main_image_processing(request, {"id": user_id}, db)
    assert response == {"task_id": "image-task", "total": 1}
    assert len(db.added) == 1

    with pytest.raises(HTTPException) as missing:
        await main.start_main_image_processing(request, {"id": user_id}, FakeDB([]))
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as ineligible:
        await main.start_main_image_processing(
            request,
            {"id": user_id},
            FakeDB([product(product_id, user_id, status="pending")]),
        )
    assert ineligible.value.status_code == 422


@pytest.mark.anyio
async def test_image_task_continues_after_failure_and_preserves_originals(monkeypatch):
    user_id = uuid.uuid4()
    first = product(uuid.uuid4(), user_id, images=["https://img.example/one.jpg"])
    second = product(uuid.uuid4(), user_id, images=["https://img.example/two.jpg"])
    originals = [list(first.images_list), list(second.images_list)]
    db = FakeDB([first, second])
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        tasks,
        "download_image",
        AsyncMock(side_effect=[b"first", ValueError("download failed")]),
    )
    monkeypatch.setattr(tasks, "process_main_image", lambda data, _: data + b"-processed")
    monkeypatch.setattr(
        tasks,
        "save_processed_image",
        lambda _, user, item: Path(f"/app/uploads/processed/{user}/{item}.jpg"),
    )
    drafted = []
    monkeypatch.setattr(
        tasks,
        "MarketplaceClient",
        lambda: SimpleNamespace(
            request_draft_generation=AsyncMock(side_effect=lambda item: drafted.append(item.id))
        ),
    )
    task = SimpleNamespace(update_state=lambda **_: None)

    result = await tasks._run_main_image_pipeline(
        task,
        str(user_id),
        [str(first.id), str(second.id)],
    )

    assert [row["status"] for row in result["completed_rows"]] == ["completed", "failed"]
    assert first.image_processing_status == "completed"
    assert second.image_processing_status == "failed"
    assert [first.images_list, second.images_list] == originals
    assert second.warnings["processing_warnings"][0]["key"] == "main_image_processing"
    assert drafted == [first.id]


class ListResult:
    def __init__(self, *, scalar_value=None, rows=None):
        self.scalar_value = scalar_value
        self.rows = rows or []

    def scalar(self):
        return self.scalar_value

    def scalars(self):
        return ScalarRows(self.rows)


class ListDB:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return ListResult(scalar_value=0) if len(self.statements) == 1 else ListResult(rows=[])


@pytest.mark.anyio
async def test_product_image_status_filter_applies_to_rows_and_count():
    db = ListDB()
    await main.list_products(
        image_processing_status="failed",
        current_user={"id": uuid.uuid4()},
        db=db,
    )

    assert len(db.statements) == 2
    for statement in db.statements:
        assert "failed" in statement.compile().params.values()
