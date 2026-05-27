import uuid
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from adapters import ADAPTERS
from clients.processor_client import ProcessorClient
from models import (
    MarketAccount,
    MarketAccountSettings,
    MarketDraftGenerationJob,
    MarketListingDraft,
)
from schemas import DraftResult
from services.draft_generation import generate_drafts_for_job


ACTIVE_STATUSES = {"generated", "needs_review", "ready", "submitting", "failed"}


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def all(self):
        if isinstance(self._value, list):
            return self._value
        return [self._value]

    def first(self):
        if isinstance(self._value, list):
            return self._value[0] if self._value else None
        return self._value


class _FakeExecuteResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return _FakeScalarResult(self._value)

    def scalar_one_or_none(self):
        if isinstance(self._value, list):
            if not self._value:
                return None
            return self._value[0]
        return self._value


class FakeDB:
    def __init__(self, accounts, drafts, *, commit_errors=None, on_rollback=None):
        self.accounts = accounts
        self.drafts = drafts
        self.added = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self.draft_lookup_compiles = []
        self.events = []
        self._commit_errors = list(commit_errors or [])
        self._on_rollback = on_rollback
        self._pending_new_drafts = []

    async def execute(self, stmt):
        model = stmt.column_descriptions[0]["entity"]
        compiled = stmt.compile()

        if model is MarketAccount:
            params = compiled.params
            user_id = next((v for k, v in params.items() if k.startswith("user_id")), None)
            connection_status = next(
                (v for k, v in params.items() if k.startswith("connection_status")),
                None,
            )
            accounts = self.accounts
            if user_id is not None:
                accounts = [account for account in accounts if account.user_id == user_id]
            if connection_status is not None:
                accounts = [
                    account
                    for account in accounts
                    if account.connection_status == connection_status
                ]
            return _FakeExecuteResult(accounts)

        if model is MarketListingDraft:
            params = compiled.params
            self.draft_lookup_compiles.append((str(compiled), params))
            source_product_id = next(
                (v for k, v in params.items() if k.startswith("source_product_id")), None
            )
            market_account_id = next(
                (v for k, v in params.items() if k.startswith("market_account_id")), None
            )
            draft_kind = next((v for k, v in params.items() if k.startswith("draft_kind")), None)
            statuses = set()
            for key, value in params.items():
                if not key.startswith("status"):
                    continue
                if isinstance(value, (list, tuple, set)):
                    statuses.update(value)
                else:
                    statuses.add(value)
            for draft in self.drafts:
                if (
                    draft.source_product_id == source_product_id
                    and draft.market_account_id == market_account_id
                    and draft.draft_kind == draft_kind
                    and draft.status in statuses
                ):
                    return _FakeExecuteResult(draft)
            return _FakeExecuteResult(None)

        raise AssertionError(f"Unexpected model query: {model}")

    def add(self, obj):
        if isinstance(obj, MarketListingDraft) and obj.id is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)
        if isinstance(obj, MarketListingDraft) and obj not in self.drafts:
            self.drafts.append(obj)
            self._pending_new_drafts.append(obj)

    async def commit(self):
        self.commit_calls += 1
        self.events.append("commit")
        if self._commit_errors:
            raise self._commit_errors.pop(0)
        self._pending_new_drafts.clear()

    async def rollback(self):
        self.rollback_calls += 1
        self.events.append("rollback")
        for draft in list(self._pending_new_drafts):
            if draft in self.drafts:
                self.drafts.remove(draft)
        self._pending_new_drafts.clear()
        if self._on_rollback is not None:
            self._on_rollback(self)


class FakeProcessorClient:
    def __init__(self, snapshots=None, *, exc=None):
        self._snapshots = snapshots or []
        self._index = 0
        self.exc = exc
        self.calls = []

    async def get_marketplace_snapshot(self, product_id, user_id):
        self.calls.append((product_id, user_id))
        if self.exc is not None:
            raise self.exc
        snapshot = self._snapshots[self._index]
        self._index += 1
        return snapshot


class FakeAdapter:
    def __init__(self, market_code):
        self.market_code = market_code
        self.calls = []

    def generate_draft(self, snapshot, settings_payload):
        self.calls.append((snapshot, settings_payload))
        return DraftResult(
            display_title=f"{self.market_code}-title",
            category_id=f"{self.market_code}-cat",
            sale_price=17200,
            cost_price=8000,
            expected_profit=4324,
            expected_margin_rate=25.14,
            primary_image_url="https://img.example/1.jpg",
            generated_payload={"market_code": self.market_code, "version": snapshot["version"]},
            validation_result={"status": "valid"},
            adapter_version=f"{self.market_code}-adapter:v1",
            recipe_versions={"title": f"{self.market_code}-title:v1"},
        )


class ExpiringAccount:
    def __init__(self, *, user_id, market_code):
        self.user_id = user_id
        self.connection_status = "connected"
        self.settings = SimpleNamespace(
            settings_schema_version="v1",
            connection_config={"connection": market_code},
            fulfillment_config={"fulfillment": market_code},
            claim_config={"claim": market_code},
            listing_defaults={"sellerCode": market_code},
            generation_rules={"pricingPolicy": {"version": f"{market_code}:v1"}},
        )
        self._id = uuid.uuid4()
        self._market_code = market_code
        self._expired = False

    def expire(self):
        self._expired = True

    @property
    def id(self):
        if self._expired:
            raise AssertionError("account.id accessed after rollback expiration")
        return self._id

    @property
    def market_code(self):
        if self._expired:
            raise AssertionError("account.market_code accessed after rollback expiration")
        return self._market_code


class ExpiringJob:
    def __init__(self, *, user_id, source_product_id):
        self.user_id = user_id
        self._source_product_id = source_product_id
        self.requested_source_version = "requested-v1"
        self.generated_source_version = None
        self.reason = "manual"
        self.status = "queued"
        self.error = {"type": "PreviousError", "message": "old"}
        self.completed_at = None
        self._expired = False

    def expire(self):
        self._expired = True

    @property
    def source_product_id(self):
        if self._expired:
            raise AssertionError("job.source_product_id accessed after rollback expiration")
        return self._source_product_id


def _snapshot(version):
    return {
        "product_id": str(uuid.uuid4()),
        "version": version,
        "refined_name": "테스트 상품",
        "market_categories": {
            "smartstore": {"category_id": "50000001"},
            "coupang": {"category_id": "12345"},
        },
        "images": {"list": ["https://img.example/1.jpg"]},
    }


def _account(user_id, market_code, connection_status="connected"):
    account_id = uuid.uuid4()
    account = MarketAccount(
        id=account_id,
        user_id=user_id,
        market_code=market_code,
        display_name=f"{market_code}-account",
        credentials_encrypted="enc",
        connection_status=connection_status,
    )
    account.settings = MarketAccountSettings(
        market_account_id=account_id,
        settings_schema_version="v1",
        connection_config={"connection": market_code},
        fulfillment_config={"fulfillment": market_code},
        claim_config={"claim": market_code},
        listing_defaults={"sellerCode": market_code},
        generation_rules={"pricingPolicy": {"version": f"{market_code}:v1"}},
    )
    return account


def _job(user_id, source_product_id):
    return MarketDraftGenerationJob(
        user_id=user_id,
        source_product_id=source_product_id,
        requested_source_version="requested-v1",
        reason="manual",
        status="queued",
        error={"type": "PreviousError", "message": "old"},
    )


@pytest.mark.asyncio
async def test_generation_creates_drafts_only_for_connected_supported_accounts():
    user_id = uuid.uuid4()
    source_product_id = uuid.uuid4()
    job = _job(user_id, source_product_id)
    accounts = [
        _account(user_id, "smartstore", "connected"),
        _account(user_id, "coupang", "connected"),
        _account(user_id, "11st", "connected"),
        _account(user_id, "smartstore", "disconnected"),
    ]
    db = FakeDB(accounts=accounts, drafts=[])
    processor_client = FakeProcessorClient([_snapshot("v1")])
    adapters = {
        "smartstore": FakeAdapter("smartstore"),
        "coupang": FakeAdapter("coupang"),
    }

    await generate_drafts_for_job(job, db, processor_client, adapters)

    created_market_codes = {draft.market_code for draft in db.drafts}
    assert created_market_codes == {"smartstore", "coupang"}
    assert len(adapters["smartstore"].calls) == 1
    assert len(adapters["coupang"].calls) == 1
    assert job.status == "completed"
    assert job.completed_at is not None
    assert job.generated_source_version == "v1"
    assert job.error is None
    assert db.commit_calls == 1


@pytest.mark.asyncio
async def test_two_runs_update_same_active_draft_and_keep_needs_review_status():
    user_id = uuid.uuid4()
    source_product_id = uuid.uuid4()
    account = _account(user_id, "smartstore", "connected")
    db = FakeDB(accounts=[account], drafts=[])
    adapters = {"smartstore": FakeAdapter("smartstore")}
    processor_client = FakeProcessorClient([_snapshot("v1"), _snapshot("v2")])

    first_job = _job(user_id, source_product_id)
    await generate_drafts_for_job(first_job, db, processor_client, adapters)
    first_draft = db.drafts[0]

    second_job = _job(user_id, source_product_id)
    await generate_drafts_for_job(second_job, db, processor_client, adapters)
    second_draft = db.drafts[0]

    assert first_draft.id == second_draft.id
    assert second_draft.source_product_version == "v2"
    assert second_draft.status == "needs_review"


@pytest.mark.asyncio
async def test_submitted_history_is_preserved_and_new_active_draft_is_created():
    user_id = uuid.uuid4()
    source_product_id = uuid.uuid4()
    account = _account(user_id, "smartstore", "connected")
    submitted_draft = MarketListingDraft(
        id=uuid.uuid4(),
        source_product_id=source_product_id,
        source_product_version="submitted-v1",
        market_account_id=account.id,
        market_code="smartstore",
        draft_kind="create",
        status="submitted",
        display_title="submitted-title",
        source_snapshot={"version": "submitted-v1"},
        generated_payload={"name": "submitted"},
        override_patch={"keep": True},
        validation_result={"status": "valid"},
        recipe_versions={"title": "v1"},
        adapter_version="smartstore-adapter:v1",
    )
    db = FakeDB(accounts=[account], drafts=[submitted_draft])
    adapters = {"smartstore": FakeAdapter("smartstore")}
    processor_client = FakeProcessorClient([_snapshot("v2")])
    job = _job(user_id, source_product_id)

    await generate_drafts_for_job(job, db, processor_client, adapters)

    assert len(db.drafts) == 2
    active_drafts = [d for d in db.drafts if d.status in ACTIVE_STATUSES]
    assert len(active_drafts) == 1
    assert active_drafts[0].id != submitted_draft.id
    assert submitted_draft.generated_payload == {"name": "submitted"}
    assert submitted_draft.display_title == "submitted-title"
    assert submitted_draft.override_patch == {"keep": True}


@pytest.mark.asyncio
async def test_generation_preserves_existing_override_patch():
    user_id = uuid.uuid4()
    source_product_id = uuid.uuid4()
    account = _account(user_id, "smartstore", "connected")
    existing_draft = MarketListingDraft(
        id=uuid.uuid4(),
        source_product_id=source_product_id,
        source_product_version="v1",
        market_account_id=account.id,
        market_code="smartstore",
        draft_kind="create",
        status="ready",
        source_snapshot={"version": "v1"},
        generated_payload={"old": True},
        override_patch={"originProduct": {"name": "수동 상품명"}},
        validation_result={"status": "valid"},
        recipe_versions={"title": "v1"},
        adapter_version="smartstore-adapter:v1",
    )
    db = FakeDB(accounts=[account], drafts=[existing_draft])
    adapters = {"smartstore": FakeAdapter("smartstore")}
    processor_client = FakeProcessorClient([_snapshot("v2")])
    job = _job(user_id, source_product_id)

    await generate_drafts_for_job(job, db, processor_client, adapters)

    assert existing_draft.override_patch == {"originProduct": {"name": "수동 상품명"}}
    assert existing_draft.status == "needs_review"


@pytest.mark.asyncio
async def test_generation_persists_pricing_summary_fields():
    user_id = uuid.uuid4()
    source_product_id = uuid.uuid4()
    account = _account(user_id, "smartstore", "connected")
    db = FakeDB(accounts=[account], drafts=[])
    adapters = {"smartstore": FakeAdapter("smartstore")}
    processor_client = FakeProcessorClient([_snapshot("v1")])
    job = _job(user_id, source_product_id)

    await generate_drafts_for_job(job, db, processor_client, adapters)

    draft = db.drafts[0]
    assert draft.cost_price == 8000
    assert draft.sale_price == 17200
    assert draft.expected_profit == 4324
    assert draft.expected_margin_rate == 25.14


@pytest.mark.asyncio
async def test_generation_sends_account_scoped_settings_to_matching_adapter():
    user_id = uuid.uuid4()
    source_product_id = uuid.uuid4()
    smartstore_account = _account(user_id, "smartstore", "connected")
    coupang_account = _account(user_id, "coupang", "connected")
    smartstore_account.settings.generation_rules = {"pricingPolicy": {"version": "smartstore-price:v2"}}
    coupang_account.settings.generation_rules = {"pricingPolicy": {"version": "coupang-price:v3"}}
    db = FakeDB(accounts=[smartstore_account, coupang_account], drafts=[])
    adapters = {
        "smartstore": FakeAdapter("smartstore"),
        "coupang": FakeAdapter("coupang"),
    }
    processor_client = FakeProcessorClient([_snapshot("v1")])
    job = _job(user_id, source_product_id)

    await generate_drafts_for_job(job, db, processor_client, adapters)

    smartstore_settings = adapters["smartstore"].calls[0][1]
    coupang_settings = adapters["coupang"].calls[0][1]
    assert smartstore_settings == {
        "settings_schema_version": "v1",
        "connection_config": {"connection": "smartstore"},
        "fulfillment_config": {"fulfillment": "smartstore"},
        "claim_config": {"claim": "smartstore"},
        "listing_defaults": {"sellerCode": "smartstore"},
        "generation_rules": {"pricingPolicy": {"version": "smartstore-price:v2"}},
    }
    assert coupang_settings == {
        "settings_schema_version": "v1",
        "connection_config": {"connection": "coupang"},
        "fulfillment_config": {"fulfillment": "coupang"},
        "claim_config": {"claim": "coupang"},
        "listing_defaults": {"sellerCode": "coupang"},
        "generation_rules": {"pricingPolicy": {"version": "coupang-price:v3"}},
    }


@pytest.mark.asyncio
async def test_generation_uses_active_status_filter_and_create_draft_kind_lookup():
    user_id = uuid.uuid4()
    source_product_id = uuid.uuid4()
    account = _account(user_id, "smartstore", "connected")
    db = FakeDB(accounts=[account], drafts=[])
    adapters = {"smartstore": FakeAdapter("smartstore")}
    processor_client = FakeProcessorClient([_snapshot("v1")])
    job = _job(user_id, source_product_id)

    await generate_drafts_for_job(job, db, processor_client, adapters)

    _sql, params = db.draft_lookup_compiles[0]
    statuses = set()
    for key, value in params.items():
        if not key.startswith("status"):
            continue
        if isinstance(value, (list, tuple, set)):
            statuses.update(value)
        else:
            statuses.add(value)
    draft_kind = next(v for k, v in params.items() if k.startswith("draft_kind"))
    assert statuses == ACTIVE_STATUSES
    assert draft_kind == "create"


@pytest.mark.asyncio
async def test_generation_failure_marks_job_failed_and_commits_then_reraises():
    user_id = uuid.uuid4()
    source_product_id = uuid.uuid4()
    job = _job(user_id, source_product_id)
    db = FakeDB(accounts=[_account(user_id, "smartstore", "connected")], drafts=[])
    processor_client = FakeProcessorClient(exc=RuntimeError("snapshot failed"))

    with pytest.raises(RuntimeError, match="snapshot failed"):
        await generate_drafts_for_job(job, db, processor_client, {"smartstore": FakeAdapter("smartstore")})

    assert job.status == "failed"
    assert job.error == {"type": "RuntimeError", "message": "snapshot failed"}
    assert db.commit_calls == 1
    assert db.rollback_calls == 1
    assert db.events == ["rollback", "commit"]


@pytest.mark.asyncio
async def test_generation_recovers_on_active_draft_integrity_contention_and_completes():
    user_id = uuid.uuid4()
    source_product_id = uuid.uuid4()
    account = _account(user_id, "smartstore", "connected")
    winner_draft = MarketListingDraft(
        id=uuid.uuid4(),
        source_product_id=source_product_id,
        source_product_version="winner-v1",
        market_account_id=account.id,
        market_code="smartstore",
        draft_kind="create",
        status="generated",
        display_title="winner-title",
        source_snapshot={"version": "winner-v1"},
        generated_payload={"winner": True},
        override_patch={"originProduct": {"name": "수동 우승자"}},
        validation_result={"status": "valid"},
        recipe_versions={"title": "winner:v1"},
        adapter_version="winner-adapter:v1",
    )

    def _inject_winner(db):
        if winner_draft not in db.drafts:
            db.drafts.append(winner_draft)

    db = FakeDB(
        accounts=[account],
        drafts=[],
        commit_errors=[
            IntegrityError(
                "INSERT INTO market_listing_drafts ...",
                {"market_account_id": str(account.id)},
                Exception("duplicate key value violates unique constraint"),
            )
        ],
        on_rollback=_inject_winner,
    )
    adapters = {"smartstore": FakeAdapter("smartstore")}
    processor_client = FakeProcessorClient([_snapshot("v2")])
    job = _job(user_id, source_product_id)

    await generate_drafts_for_job(job, db, processor_client, adapters)

    active_drafts = [d for d in db.drafts if d.status in ACTIVE_STATUSES]
    assert len(active_drafts) == 1
    assert active_drafts[0].id == winner_draft.id
    assert active_drafts[0].source_product_version == "v2"
    assert active_drafts[0].status == "needs_review"
    assert active_drafts[0].override_patch == {"originProduct": {"name": "수동 우승자"}}
    assert job.status == "completed"
    assert job.error is None
    assert db.commit_calls == 2
    assert db.rollback_calls == 1
    assert db.events == ["commit", "rollback", "commit"]


@pytest.mark.asyncio
async def test_generation_retry_after_rollback_uses_scalar_targets_not_expired_objects():
    # `aiosqlite` is not available in this repo, so this regression test uses
    # expiring fakes to simulate AsyncSession rollback expiration semantics.
    user_id = uuid.uuid4()
    source_product_id = uuid.uuid4()
    account = ExpiringAccount(user_id=user_id, market_code="smartstore")
    job = ExpiringJob(user_id=user_id, source_product_id=source_product_id)
    winner_draft = MarketListingDraft(
        id=uuid.uuid4(),
        source_product_id=source_product_id,
        source_product_version="winner-v1",
        market_account_id=account.id,
        market_code="smartstore",
        draft_kind="create",
        status="generated",
        source_snapshot={"version": "winner-v1"},
        generated_payload={"winner": True},
        validation_result={"status": "valid"},
        recipe_versions={"title": "winner:v1"},
        adapter_version="winner-adapter:v1",
    )

    def _expire_and_inject_winner(db):
        account.expire()
        job.expire()
        if winner_draft not in db.drafts:
            db.drafts.append(winner_draft)

    db = FakeDB(
        accounts=[account],
        drafts=[],
        commit_errors=[
            IntegrityError(
                "INSERT INTO market_listing_drafts ...",
                {"market_account_id": str(account.id)},
                Exception("duplicate key value violates unique constraint"),
            )
        ],
        on_rollback=_expire_and_inject_winner,
    )
    adapters = {"smartstore": FakeAdapter("smartstore")}
    processor_client = FakeProcessorClient([_snapshot("v2")])

    await generate_drafts_for_job(job, db, processor_client, adapters)

    active_drafts = [d for d in db.drafts if d.status in ACTIVE_STATUSES]
    assert len(active_drafts) == 1
    assert active_drafts[0].id == winner_draft.id
    assert active_drafts[0].source_product_version == "v2"
    assert job.status == "completed"
    assert db.commit_calls == 2
    assert db.rollback_calls == 1


@pytest.mark.asyncio
async def test_processor_client_uses_expected_headers_path_and_query(monkeypatch):
    captured = {}
    payload = {"version": "v1"}

    async def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["query"] = parse_qs(request.url.query.decode())
        captured["token"] = request.headers.get("X-Internal-Service-Token")
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    class _PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            captured["base_url"] = str(kwargs.get("base_url"))
            captured["timeout"] = kwargs.get("timeout")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("clients.processor_client.httpx.AsyncClient", _PatchedAsyncClient)
    client = ProcessorClient()
    result = await client.get_marketplace_snapshot("product-1", "user-1")

    assert result == payload
    assert captured["method"] == "GET"
    assert captured["path"] == "/internal/products/product-1/marketplace-snapshot"
    assert captured["query"] == {"user_id": ["user-1"]}
    assert captured["token"] == "internal-test-token"
    assert captured["base_url"] == "http://processor:8002"
    assert captured["timeout"] == 10.0

    monkeypatch.setattr("clients.processor_client.httpx.AsyncClient", real_async_client)


def test_adapter_registry_exposes_supported_markets():
    assert set(ADAPTERS.keys()) == {"smartstore", "coupang"}
