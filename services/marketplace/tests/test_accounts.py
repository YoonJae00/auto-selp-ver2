import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from auth import get_current_user, require_internal_service_token
from config import settings
from database import get_db
from main import app
from models import MarketAccount, MarketAccountSettings
from security import decrypt_credentials


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


class FakeAsyncSession:
    def __init__(self, *, accounts=None, settings_by_account_id=None):
        self.accounts = list(accounts or [])
        self.accounts_by_id = {account.id: account for account in self.accounts}
        self.settings_by_account_id = dict(settings_by_account_id or {})
        self.added = []
        self.last_execute_sql = ""
        self.last_execute_params = {}

    async def execute(self, stmt):
        sql = str(stmt)
        params = stmt.compile().params
        self.last_execute_sql = sql
        self.last_execute_params = params

        if "FROM market_accounts" in sql:
            account_id = params.get("id_1")
            user_id = params.get("user_id_1")
            if account_id is not None:
                account = self.accounts_by_id.get(account_id)
                if account and account.user_id == user_id:
                    return FakeResult([account])
                return FakeResult([])
            if user_id is None:
                raise AssertionError("Expected user ownership filter for account listing")
            return FakeResult([a for a in self.accounts if a.user_id == user_id])

        if "FROM market_account_settings" in sql:
            account_id = params.get("market_account_id_1")
            setting = self.settings_by_account_id.get(account_id)
            return FakeResult([setting] if setting else [])

        raise AssertionError(f"Unexpected query: {sql}")

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, MarketAccount):
            self.accounts.append(obj)
            self.accounts_by_id[obj.id] = obj
        if isinstance(obj, MarketAccountSettings):
            self.settings_by_account_id[obj.market_account_id] = obj

    async def commit(self):
        return None

    async def refresh(self, obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = now
        obj.updated_at = now
        if isinstance(obj, MarketAccount):
            if getattr(obj, "connection_status", None) is None:
                obj.connection_status = "connected"
            if getattr(obj, "is_primary", None) is None:
                obj.is_primary = True


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _account(user_id: uuid.UUID, market_code: str, display_name: str) -> MarketAccount:
    now = datetime.now(timezone.utc)
    return MarketAccount(
        id=uuid.uuid4(),
        user_id=user_id,
        market_code=market_code,
        display_name=display_name,
        credentials_encrypted="encrypted",
        connection_status="connected",
        is_primary=True,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_create_account_derives_owner_encrypts_credentials_and_redacts_response():
    owner_id = uuid.uuid4()
    fake_db = FakeAsyncSession()

    async def override_get_current_user():
        return {"id": owner_id, "username": "owner", "is_admin": False}

    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    payload = {
        "market_code": "smartstore",
        "display_name": "Main SmartStore",
        "credentials": {"client_id": "abc", "client_secret": "super-secret"},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/accounts", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert "user_id" not in body
    assert "credentials" not in body
    assert "credentials_encrypted" not in body

    created = fake_db.added[0]
    assert isinstance(created, MarketAccount)
    assert created.user_id == owner_id
    assert created.credentials_encrypted != payload["credentials"]["client_secret"]
    assert decrypt_credentials(created.credentials_encrypted) == payload["credentials"]


@pytest.mark.asyncio
async def test_list_accounts_is_scoped_to_authenticated_owner():
    owner_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    owner_account = _account(owner_id, "smartstore", "Owner account")
    other_account = _account(other_user_id, "coupang", "Other account")
    fake_db = FakeAsyncSession(accounts=[owner_account, other_account])

    async def override_get_current_user():
        return {"id": owner_id, "username": "owner", "is_admin": False}

    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/accounts")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(owner_account.id)
    assert fake_db.last_execute_params.get("user_id_1") == owner_id


@pytest.mark.asyncio
async def test_update_account_settings_upserts_market_specific_json_including_pricing_policy():
    owner_id = uuid.uuid4()
    account = _account(owner_id, "smartstore", "Owner account")
    fake_db = FakeAsyncSession(accounts=[account])

    async def override_get_current_user():
        return {"id": owner_id, "username": "owner", "is_admin": False}

    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    payload = {
        "settings_schema_version": "v1",
        "fulfillment_config": {
            "smartstore": {"shippingPolicyId": 111},
            "coupang": {"outboundShippingTimeDay": 2},
        },
        "claim_config": {
            "smartstore": {"returnAddressId": 77},
            "coupang": {"vendorReturnCenterCode": "VRC001"},
        },
        "listing_defaults": {
            "smartstore": {"adultOnly": False},
            "coupang": {"parallelImported": "NOT_PARALLEL_IMPORTED"},
        },
        "generation_rules": {
            "pricingPolicy": {"markupRate": 1.15, "minMarginWon": 4000},
            "titlePolicy": {"suffix": "[공식]"},
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(f"/accounts/{account.id}/settings", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["market_account_id"] == str(account.id)
    assert body["generation_rules"]["pricingPolicy"]["minMarginWon"] == 4000
    assert fake_db.settings_by_account_id[account.id].generation_rules["pricingPolicy"] == {
        "markupRate": 1.15,
        "minMarginWon": 4000,
    }


@pytest.mark.asyncio
async def test_update_account_settings_returns_404_for_non_owner_account():
    account_owner_id = uuid.uuid4()
    requester_id = uuid.uuid4()
    account = _account(account_owner_id, "smartstore", "Owned by someone else")
    fake_db = FakeAsyncSession(accounts=[account])

    async def override_get_current_user():
        return {"id": requester_id, "username": "requester", "is_admin": False}

    async def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(
            f"/accounts/{account.id}/settings",
            json={"generation_rules": {"pricingPolicy": {"markupRate": 1.2}}},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Market account not found"


@pytest.mark.asyncio
async def test_require_internal_service_token_accepts_matching_token():
    await require_internal_service_token(settings.INTERNAL_SERVICE_TOKEN)


@pytest.mark.asyncio
async def test_require_internal_service_token_rejects_invalid_token():
    with pytest.raises(HTTPException) as exc_info:
        await require_internal_service_token("invalid-token")

    assert exc_info.value.status_code == 401
