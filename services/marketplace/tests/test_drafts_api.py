import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from auth import get_current_user
from database import get_db
from main import app
from models import MarketAccount, MarketListingDraft


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


class FakeDraftsDB:
    def __init__(self, accounts, drafts):
        self.accounts = {account.id: account for account in accounts}
        self.drafts = list(drafts)
        self.last_execute_sql = ""
        self.last_execute_params = {}

    async def execute(self, stmt):
        sql = str(stmt)
        params = stmt.compile().params
        self.last_execute_sql = sql
        self.last_execute_params = params

        if "FROM market_listing_drafts JOIN market_accounts" not in sql:
            raise AssertionError(f"Unexpected query: {sql}")

        owned_rows = [
            draft
            for draft in self.drafts
            if self.accounts[draft.market_account_id].user_id
            == _first_param_by_prefix(params, "user_id")
        ]

        market_code = _first_param_by_prefix(params, "market_code")
        if market_code is not None:
            owned_rows = [row for row in owned_rows if row.market_code == market_code]

        status = _first_param_by_prefix(params, "status")
        if status is not None:
            owned_rows = [row for row in owned_rows if row.status == status]

        draft_id = _first_param_by_prefix(params, "id")
        if draft_id is not None:
            owned_rows = [row for row in owned_rows if row.id == draft_id]

        owned_rows.sort(key=lambda row: row.updated_at, reverse=True)
        return FakeResult(owned_rows)


def _first_param_by_prefix(params: dict, prefix: str):
    for key, value in params.items():
        if key.startswith(prefix):
            return value
    return None


def _account(user_id: uuid.UUID) -> MarketAccount:
    now = datetime.now(timezone.utc)
    return MarketAccount(
        id=uuid.uuid4(),
        user_id=user_id,
        market_code="smartstore",
        display_name="Owner account",
        credentials_encrypted="encrypted",
        connection_status="connected",
        is_primary=True,
        created_at=now,
        updated_at=now,
    )


def _draft(
    *,
    account_id: uuid.UUID,
    market_code: str,
    status: str,
    updated_at: datetime,
) -> MarketListingDraft:
    return MarketListingDraft(
        id=uuid.uuid4(),
        source_product_id=uuid.uuid4(),
        source_product_version="2026-05-28T10:20:00+00:00",
        market_account_id=account_id,
        market_code=market_code,
        draft_kind="create",
        status=status,
        display_title=f"{market_code}-{status}",
        category_id="50000123",
        sale_price=17500,
        cost_price=8000,
        expected_profit=4300,
        expected_margin_rate=24.57,
        primary_image_url="https://example.com/main.jpg",
        source_snapshot={"version": "2026-05-28T10:20:00+00:00"},
        generated_payload={"name": "generated"},
        override_patch={"name": "manual"},
        validation_result={"status": "valid"},
        recipe_versions={"pricing": "price:v1"},
        adapter_version="smartstore:v1",
        remote_product_id=None,
        created_at=updated_at,
        updated_at=updated_at,
    )


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_drafts_returns_only_authenticated_users_drafts_with_filters():
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    owner_account = _account(owner_id)
    other_account = _account(other_id)
    now = datetime.now(timezone.utc)

    owned_match = _draft(
        account_id=owner_account.id,
        market_code="smartstore",
        status="needs_review",
        updated_at=now,
    )
    owned_non_match = _draft(
        account_id=owner_account.id,
        market_code="coupang",
        status="needs_review",
        updated_at=now - timedelta(minutes=5),
    )
    others = _draft(
        account_id=other_account.id,
        market_code="smartstore",
        status="needs_review",
        updated_at=now - timedelta(minutes=10),
    )

    fake_db = FakeDraftsDB([owner_account, other_account], [others, owned_non_match, owned_match])

    async def override_get_current_user():
        return {"id": owner_id, "username": "owner", "is_admin": False}

    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/drafts",
            params={"market_code": "smartstore", "status": "needs_review"},
        )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [str(owned_match.id)]
    assert fake_db.last_execute_params.get("user_id_1") == owner_id


@pytest.mark.asyncio
async def test_get_draft_scopes_by_owner_and_returns_inbox_payload_fields():
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    owner_account = _account(owner_id)
    other_account = _account(other_id)
    now = datetime.now(timezone.utc)

    owned_draft = _draft(
        account_id=owner_account.id,
        market_code="smartstore",
        status="needs_review",
        updated_at=now,
    )
    other_draft = _draft(
        account_id=other_account.id,
        market_code="smartstore",
        status="needs_review",
        updated_at=now - timedelta(minutes=1),
    )

    fake_db = FakeDraftsDB([owner_account, other_account], [owned_draft, other_draft])

    async def override_get_current_user():
        return {"id": owner_id, "username": "owner", "is_admin": False}

    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        success = await client.get(f"/drafts/{owned_draft.id}")
        missing = await client.get(f"/drafts/{other_draft.id}")

    assert success.status_code == 200
    body = success.json()
    assert body["id"] == str(owned_draft.id)
    assert body["generated_payload"] == {"name": "generated"}
    assert body["validation_result"] == {"status": "valid"}
    assert body["recipe_versions"] == {"pricing": "price:v1"}
    assert body["source_snapshot"] == {"version": "2026-05-28T10:20:00+00:00"}
    assert body["market_account_id"] == str(owner_account.id)

    assert missing.status_code == 404
    assert missing.json()["detail"] == "Draft not found"
