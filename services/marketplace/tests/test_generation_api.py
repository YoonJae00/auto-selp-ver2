import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

import main as main_module
import tasks as tasks_module
from database import get_db
from main import app
from models import MarketDraftGenerationJob


class FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one(self):
        if self._row is None:
            raise AssertionError("Expected a queued generation job")
        return self._row


class FakeQueueDB:
    def __init__(self):
        self.jobs = []

    async def execute(self, _stmt):
        if not self.jobs:
            return FakeResult(None)
        return FakeResult(self.jobs[0])

    def add(self, obj):
        if isinstance(obj, MarketDraftGenerationJob):
            self.jobs.append(obj)

    async def commit(self):
        return None

    async def refresh(self, obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = now
        obj.updated_at = now


class FakeSessionContextManager:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_internal_generation_endpoint_requires_service_token():
    payload = {
        "source_product_id": str(uuid.uuid4()),
        "source_product_updated_at": "2026-05-28T10:20:00+00:00",
        "source_user_id": str(uuid.uuid4()),
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/internal/draft-generation-jobs", json=payload)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_internal_generation_endpoint_creates_job_and_queues_task(monkeypatch):
    fake_db = FakeQueueDB()
    queued_job_ids = []

    class QueueSpy:
        @staticmethod
        def delay(job_id: str):
            queued_job_ids.append(job_id)

    monkeypatch.setattr(main_module, "generate_market_listing_drafts", QueueSpy, raising=False)

    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db

    payload = {
        "source_product_id": str(uuid.uuid4()),
        "source_product_updated_at": "2026-05-28T10:20:00+00:00",
        "source_user_id": str(uuid.uuid4()),
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/internal/draft-generation-jobs",
            json=payload,
            headers={"X-Internal-Service-Token": "internal-test-token"},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["reason"] == "processing_completed"
    assert queued_job_ids == [body["id"]]
    assert fake_db.jobs[0].requested_source_version == "2026-05-28T10:20:00+00:00"


@pytest.mark.asyncio
async def test_run_generation_job_loads_job_from_new_session_and_delegates(monkeypatch):
    fake_db = FakeQueueDB()
    queued_job = MarketDraftGenerationJob(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        source_product_id=uuid.uuid4(),
        requested_source_version="2026-05-28T10:20:00+00:00",
        generated_source_version=None,
        reason="processing_completed",
        status="queued",
        error=None,
    )
    fake_db.add(queued_job)

    calls = []

    class ProcessorClientStub:
        pass

    async def fake_generate_drafts_for_job(job, db, processor_client):
        calls.append((job, db, processor_client))
        job.status = "completed"

    monkeypatch.setattr(tasks_module, "SessionLocal", lambda: FakeSessionContextManager(fake_db))
    monkeypatch.setattr(tasks_module, "ProcessorClient", ProcessorClientStub)
    monkeypatch.setattr(tasks_module, "generate_drafts_for_job", fake_generate_drafts_for_job)

    result = await tasks_module._run_generation_job(str(queued_job.id))

    assert result == {"job_id": str(queued_job.id), "status": "completed"}
    assert len(calls) == 1
    assert calls[0][0] is queued_job
    assert calls[0][1] is fake_db
    assert isinstance(calls[0][2], ProcessorClientStub)
