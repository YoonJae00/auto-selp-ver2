import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models import (
    MarketAccount,
    MarketAccountSettings,
    MarketDraftGenerationJob,
    MarketListingDraft,
)
from schemas import DraftResult
from services.draft_generation import generate_drafts_for_job


MARKETPLACE_TEST_DATABASE_URL = os.getenv("MARKETPLACE_TEST_DATABASE_URL")
ACTIVE_STATUSES = {"generated", "needs_review", "ready", "submitting", "failed"}
INTERLEAVING_TIMEOUT_SECONDS = 10

pytestmark = pytest.mark.skipif(
    not MARKETPLACE_TEST_DATABASE_URL,
    reason="MARKETPLACE_TEST_DATABASE_URL is not set",
)


class StubProcessorClient:
    def __init__(self, snapshot):
        self._snapshot = snapshot
        self.calls = []

    async def get_marketplace_snapshot(self, product_id, user_id):
        self.calls.append((product_id, user_id))
        return self._snapshot


class StubAdapter:
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
            generated_payload={
                "market_code": self.market_code,
                "version": snapshot["version"],
            },
            validation_result={"status": "valid"},
            adapter_version=f"{self.market_code}-adapter:v2",
            recipe_versions={"title": f"{self.market_code}-title:v2"},
        )


@pytest_asyncio.fixture
async def pg_sessionmaker():
    schema_name = f"marketplace_it_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(MARKETPLACE_TEST_DATABASE_URL)
    async with admin_engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))

    engine = create_async_engine(
        MARKETPLACE_TEST_DATABASE_URL,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(MarketAccount.__table__.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        yield session_maker
    finally:
        await engine.dispose()
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        await admin_engine.dispose()


def _account(user_id, market_code="smartstore"):
    account = MarketAccount(
        id=uuid.uuid4(),
        user_id=user_id,
        market_code=market_code,
        display_name=f"{market_code}-account",
        credentials_encrypted="enc",
        connection_status="connected",
        is_primary=True,
    )
    account.settings = MarketAccountSettings(
        market_account_id=account.id,
        settings_schema_version="v1",
        connection_config={"connection": market_code},
        fulfillment_config={"fulfillment": market_code},
        claim_config={"claim": market_code},
        listing_defaults={"sellerCode": market_code},
        generation_rules={"pricingPolicy": {"version": f"{market_code}-policy:v1"}},
    )
    return account


def _job(user_id, source_product_id):
    return MarketDraftGenerationJob(
        id=uuid.uuid4(),
        user_id=user_id,
        source_product_id=source_product_id,
        requested_source_version="v0",
        reason="manual",
        status="queued",
    )


def _snapshot(version):
    return {
        "version": version,
        "name": f"name-{version}",
        "price_retail": 10000,
        "price_min": 10000,
    }


@pytest.mark.asyncio
async def test_pg_generation_interleaved_older_update_does_not_overwrite_newer_committed_update(
    pg_sessionmaker,
):
    user_id = uuid.uuid4()
    source_product_id = uuid.uuid4()
    account = _account(user_id)
    older_job = _job(user_id, source_product_id)
    newer_job = _job(user_id, source_product_id)
    draft_id = uuid.uuid4()

    async with pg_sessionmaker() as session:
        session.add(account)
        session.add(older_job)
        session.add(newer_job)
        session.add(
            MarketListingDraft(
                id=draft_id,
                source_product_id=source_product_id,
                source_product_version="2026-05-28T08:00:00+00:00",
                market_account_id=account.id,
                market_code="smartstore",
                draft_kind="create",
                status="needs_review",
                display_title="baseline-title",
                source_snapshot={"version": "2026-05-28T08:00:00+00:00"},
                generated_payload={"market_code": "smartstore", "version": "baseline"},
                validation_result={"status": "valid"},
                recipe_versions={"title": "baseline-title:v1"},
                adapter_version="smartstore-adapter:baseline",
            )
        )
        await session.commit()

    update_entered = asyncio.Event()
    allow_older_update = asyncio.Event()
    older_update_intercepted = {"done": False}

    async with pg_sessionmaker() as older_session, pg_sessionmaker() as newer_session:
        older_job_run = await older_session.get(MarketDraftGenerationJob, older_job.id)
        newer_job_run = await newer_session.get(MarketDraftGenerationJob, newer_job.id)

        real_older_execute = older_session.execute

        async def interleaved_older_execute(stmt, *args, **kwargs):
            if (
                not older_update_intercepted["done"]
                and getattr(stmt, "__visit_name__", None) == "update"
                and getattr(getattr(stmt, "table", None), "name", None)
                == MarketListingDraft.__tablename__
            ):
                older_update_intercepted["done"] = True
                update_entered.set()
                await allow_older_update.wait()
            return await real_older_execute(stmt, *args, **kwargs)

        older_session.execute = interleaved_older_execute

        older_task = asyncio.create_task(
            generate_drafts_for_job(
                older_job_run,
                older_session,
                StubProcessorClient(_snapshot("2026-05-28T09:00:00+00:00")),
                {"smartstore": StubAdapter("smartstore")},
            )
        )
        try:
            await asyncio.wait_for(
                update_entered.wait(),
                timeout=INTERLEAVING_TIMEOUT_SECONDS,
            )

            await asyncio.wait_for(
                generate_drafts_for_job(
                    newer_job_run,
                    newer_session,
                    StubProcessorClient(_snapshot("2026-05-28T10:00:00+00:00")),
                    {"smartstore": StubAdapter("smartstore")},
                ),
                timeout=INTERLEAVING_TIMEOUT_SECONDS,
            )

            allow_older_update.set()
            await asyncio.wait_for(
                older_task,
                timeout=INTERLEAVING_TIMEOUT_SECONDS,
            )
        finally:
            allow_older_update.set()
            if not older_task.done():
                older_task.cancel()
            await asyncio.gather(older_task, return_exceptions=True)

    async with pg_sessionmaker() as session:
        persisted = await session.get(MarketListingDraft, draft_id)
        older_job_after = await session.get(MarketDraftGenerationJob, older_job.id)
        newer_job_after = await session.get(MarketDraftGenerationJob, newer_job.id)
        all_drafts = (await session.execute(select(MarketListingDraft))).scalars().all()

    assert len(all_drafts) == 1
    assert persisted is not None
    assert persisted.source_product_version == "2026-05-28T10:00:00+00:00"
    assert persisted.generated_payload == {"market_code": "smartstore", "version": "2026-05-28T10:00:00+00:00"}
    assert persisted.status == "needs_review"
    assert older_job_after is not None
    assert older_job_after.status == "completed"
    assert older_job_after.generated_source_version == "2026-05-28T09:00:00+00:00"
    assert older_job_after.error is None
    assert newer_job_after is not None
    assert newer_job_after.status == "completed"
    assert newer_job_after.generated_source_version == "2026-05-28T10:00:00+00:00"
    assert newer_job_after.error is None


@pytest.mark.asyncio
async def test_pg_generation_does_not_regenerate_when_draft_becomes_submitting_before_update(
    pg_sessionmaker,
):
    user_id = uuid.uuid4()
    source_product_id = uuid.uuid4()
    account = _account(user_id)
    job = _job(user_id, source_product_id)
    draft_id = uuid.uuid4()

    async with pg_sessionmaker() as session:
        session.add(account)
        session.add(job)
        session.add(
            MarketListingDraft(
                id=draft_id,
                source_product_id=source_product_id,
                source_product_version="2026-05-28T08:00:00+00:00",
                market_account_id=account.id,
                market_code="smartstore",
                draft_kind="create",
                status="ready",
                display_title="ready-title",
                source_snapshot={"version": "2026-05-28T08:00:00+00:00"},
                generated_payload={"market_code": "smartstore", "version": "ready"},
                validation_result={"status": "valid"},
                recipe_versions={"title": "ready-title:v1"},
                adapter_version="smartstore-adapter:ready",
            )
        )
        await session.commit()

    async with pg_sessionmaker() as session:
        run_job = await session.get(MarketDraftGenerationJob, job.id)
        adapter = StubAdapter("smartstore")
        processor_client = StubProcessorClient(_snapshot("2026-05-28T09:00:00+00:00"))
        real_execute = session.execute
        switched = {"done": False}

        async def execute_with_transition(stmt, *args, **kwargs):
            if (
                not switched["done"]
                and getattr(stmt, "__visit_name__", None) == "update"
                and getattr(getattr(stmt, "table", None), "name", None)
                == MarketListingDraft.__tablename__
            ):
                switched["done"] = True
                async with pg_sessionmaker() as contender_session:
                    contender_draft = await contender_session.get(MarketListingDraft, draft_id)
                    contender_draft.status = "submitting"
                    await contender_session.commit()
            return await real_execute(stmt, *args, **kwargs)

        session.execute = execute_with_transition
        await generate_drafts_for_job(
            run_job,
            session,
            processor_client,
            {"smartstore": adapter},
        )

    async with pg_sessionmaker() as session:
        all_drafts = (await session.execute(select(MarketListingDraft))).scalars().all()
        persisted = await session.get(MarketListingDraft, draft_id)
        job_after = await session.get(MarketDraftGenerationJob, job.id)

    assert len(all_drafts) == 1
    assert persisted is not None
    assert persisted.status == "submitting"
    assert persisted.source_product_version == "2026-05-28T08:00:00+00:00"
    assert persisted.generated_payload == {"market_code": "smartstore", "version": "ready"}
    assert job_after is not None
    assert job_after.status == "completed"
    assert job_after.generated_source_version == "2026-05-28T09:00:00+00:00"
    assert job_after.error is None


@pytest.mark.asyncio
async def test_pg_generation_retries_active_draft_insert_contention_preserving_overrides_and_audit(
    pg_sessionmaker,
):
    user_id = uuid.uuid4()
    source_product_id = uuid.uuid4()
    account = _account(user_id)
    job = _job(user_id, source_product_id)
    winner_draft_id = uuid.uuid4()

    async with pg_sessionmaker() as session:
        session.add(account)
        session.add(job)
        await session.commit()

    async with pg_sessionmaker() as session:
        run_job = await session.get(MarketDraftGenerationJob, job.id)
        adapter = StubAdapter("smartstore")
        processor_client = StubProcessorClient(_snapshot("2026-05-28T09:00:00+00:00"))
        real_commit = session.commit
        injected = {"done": False}

        async def commit_with_contention():
            if not injected["done"]:
                injected["done"] = True
                async with pg_sessionmaker() as contender_session:
                    contender_session.add(
                        MarketListingDraft(
                            id=winner_draft_id,
                            source_product_id=source_product_id,
                            source_product_version="2026-05-28T08:00:00+00:00",
                            market_account_id=account.id,
                            market_code="smartstore",
                            draft_kind="create",
                            status="generated",
                            display_title="winner-title",
                            source_snapshot={"version": "2026-05-28T08:00:00+00:00"},
                            generated_payload={"winner": True},
                            override_patch={"originProduct": {"name": "수동 우승자"}},
                            validation_result={"status": "valid"},
                            recipe_versions={"title": "winner-title:v1"},
                            adapter_version="winner-adapter:v1",
                        )
                    )
                    await contender_session.commit()
            await real_commit()

        session.commit = commit_with_contention
        await generate_drafts_for_job(
            run_job,
            session,
            processor_client,
            {"smartstore": adapter},
        )

    async with pg_sessionmaker() as session:
        active_drafts = (
            await session.execute(
                select(MarketListingDraft).where(
                    MarketListingDraft.status.in_(ACTIVE_STATUSES)
                )
            )
        ).scalars().all()
        winner = await session.get(MarketListingDraft, winner_draft_id)
        job_after = await session.get(MarketDraftGenerationJob, job.id)

    assert len(active_drafts) == 1
    assert winner is not None
    assert active_drafts[0].id == winner_draft_id
    assert winner.source_product_version == "2026-05-28T09:00:00+00:00"
    assert winner.status == "needs_review"
    assert winner.override_patch == {"originProduct": {"name": "수동 우승자"}}
    assert job_after is not None
    assert job_after.status == "completed"
    assert job_after.generated_source_version == "2026-05-28T09:00:00+00:00"
    assert job_after.error is None
    assert job_after.completed_at is not None
