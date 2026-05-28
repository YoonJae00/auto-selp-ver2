import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from auth import get_current_user
from database import get_db
from main import app
from models import (
    MarketAccount,
    MarketListingDraft,
    MarketSubmissionAttempt,
    MarketSubmissionJob,
)


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class FakeSubmissionDB:
    def __init__(self, accounts, drafts):
        self.accounts = {account.id: account for account in accounts}
        self.drafts = list(drafts)
        self.jobs = []
        self.attempts = []
        self.commits = 0

    async def execute(self, stmt):
        sql = str(stmt)
        params = stmt.compile().params

        if "FROM market_accounts" in sql:
            account_id = _first_param_by_prefix(params, "id")
            user_id = _first_param_by_prefix(params, "user_id")
            rows = [
                account
                for account in self.accounts.values()
                if (account_id is None or account.id == account_id)
                and (user_id is None or account.user_id == user_id)
            ]
            return FakeResult(rows)

        if "FROM market_listing_drafts" in sql:
            draft_ids = _first_param_by_prefix(params, "id")
            if draft_ids is None:
                draft_ids = _first_param_by_prefix(params, "id_1")
            if not isinstance(draft_ids, list):
                draft_ids = [draft_ids] if draft_ids is not None else None

            market_account_id = _first_param_by_prefix(params, "market_account_id")
            rows = [
                draft
                for draft in self.drafts
                if (draft_ids is None or draft.id in draft_ids)
                and (
                    market_account_id is None
                    or draft.market_account_id == market_account_id
                )
            ]
            return FakeResult(rows)

        if "FROM market_submission_jobs" in sql:
            user_id = _first_param_by_prefix(params, "user_id")
            rows = [job for job in self.jobs if user_id is None or job.user_id == user_id]
            rows.sort(key=lambda row: row.created_at, reverse=True)
            return FakeResult(rows)

        raise AssertionError(f"Unexpected query: {sql}")

    def add(self, obj):
        if isinstance(obj, MarketSubmissionJob):
            self.jobs.append(obj)
        elif isinstance(obj, MarketSubmissionAttempt):
            self.attempts.append(obj)
        else:
            raise AssertionError(f"Unexpected add: {obj!r}")

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime.now(timezone.utc)


def _first_param_by_prefix(params: dict, prefix: str):
    for key, value in params.items():
        if key.startswith(prefix):
            return value
    return None


def _account(user_id: uuid.UUID, market_code="smartstore") -> MarketAccount:
    now = datetime.now(timezone.utc)
    return MarketAccount(
        id=uuid.uuid4(),
        user_id=user_id,
        market_code=market_code,
        display_name="Main account",
        credentials_encrypted="encrypted",
        connection_status="connected",
        is_primary=True,
        created_at=now,
        updated_at=now,
    )


def _draft(account: MarketAccount, *, status="ready", validation_status="valid"):
    now = datetime.now(timezone.utc)
    return MarketListingDraft(
        id=uuid.uuid4(),
        source_product_id=uuid.uuid4(),
        source_product_version="v1",
        market_account_id=account.id,
        market_code=account.market_code,
        draft_kind="create",
        status=status,
        display_title="등록 대상 상품",
        category_id="50000123",
        sale_price=17200,
        cost_price=8000,
        expected_profit=4300,
        expected_margin_rate=25.0,
        primary_image_url="https://example.com/main.jpg",
        source_snapshot={"origin": "중국"},
        generated_payload={"originProduct": {"name": "등록 대상 상품"}},
        override_patch=None,
        validation_result={"status": validation_status},
        recipe_versions={"title": "smartstore-title:v1"},
        adapter_version="smartstore-adapter:v1",
        remote_product_id=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_patch_draft_applies_overrides_and_marks_ready_for_owner():
    user_id = uuid.uuid4()
    account = _account(user_id)
    draft = _draft(account, status="needs_review")
    fake_db = FakeSubmissionDB([account], [draft])

    async def override_get_current_user():
        return {"id": user_id, "username": "owner", "is_admin": False}

    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/drafts/{draft.id}",
            json={
                "status": "ready",
                "override_patch": {"originProduct": {"name": "수정 상품명"}},
            },
        )

    assert response.status_code == 200
    assert draft.status == "ready"
    assert draft.override_patch == {"originProduct": {"name": "수정 상품명"}}
    assert response.json()["override_patch"] == {"originProduct": {"name": "수정 상품명"}}


@pytest.mark.asyncio
async def test_create_submission_job_records_attempts_for_valid_owned_drafts():
    user_id = uuid.uuid4()
    account = _account(user_id)
    ready_draft = _draft(account, status="ready")
    fake_db = FakeSubmissionDB([account], [ready_draft])

    async def override_get_current_user():
        return {"id": user_id, "username": "owner", "is_admin": False}

    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/submissions",
            json={"market_account_id": str(account.id), "draft_ids": [str(ready_draft.id)]},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["draft_count"] == 1
    assert len(fake_db.jobs) == 1
    assert len(fake_db.attempts) == 1
    assert fake_db.attempts[0].draft_id == ready_draft.id
    assert fake_db.attempts[0].submitted_payload == ready_draft.generated_payload
    assert ready_draft.status == "submitting"


@pytest.mark.asyncio
async def test_create_submission_job_rejects_blocked_drafts_without_attempts():
    user_id = uuid.uuid4()
    account = _account(user_id)
    blocked_draft = _draft(account, status="ready", validation_status="blocked")
    fake_db = FakeSubmissionDB([account], [blocked_draft])

    async def override_get_current_user():
        return {"id": user_id, "username": "owner", "is_admin": False}

    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/submissions",
            json={"market_account_id": str(account.id), "draft_ids": [str(blocked_draft.id)]},
        )

    assert response.status_code == 422
    assert "blocked" in response.json()["detail"]
    assert fake_db.jobs == []
    assert fake_db.attempts == []
