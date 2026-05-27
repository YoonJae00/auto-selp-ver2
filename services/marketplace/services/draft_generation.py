from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from adapters import ADAPTERS
from models import MarketAccount, MarketAccountSettings, MarketListingDraft

MUTABLE_DRAFT_STATUSES = (
    "generated",
    "needs_review",
    "ready",
    "failed",
)
SUBMITTING_DRAFT_STATUS = "submitting"


@dataclass(frozen=True)
class DraftTarget:
    market_account_id: Any
    market_code: str
    result: Any


def _serialize_settings(account_settings: MarketAccountSettings | None) -> dict[str, Any]:
    if account_settings is None:
        return {
            "settings_schema_version": "v1",
            "connection_config": None,
            "fulfillment_config": None,
            "claim_config": None,
            "listing_defaults": None,
            "generation_rules": None,
        }
    return {
        "settings_schema_version": account_settings.settings_schema_version,
        "connection_config": account_settings.connection_config,
        "fulfillment_config": account_settings.fulfillment_config,
        "claim_config": account_settings.claim_config,
        "listing_defaults": account_settings.listing_defaults,
        "generation_rules": account_settings.generation_rules,
    }


async def _load_connected_accounts(db, user_id):
    result = await db.execute(
        select(MarketAccount)
        .where(
            MarketAccount.user_id == user_id,
            MarketAccount.connection_status == "connected",
        )
        .options(selectinload(MarketAccount.settings))
    )
    return result.scalars().all()


async def _load_create_draft_by_statuses(db, source_product_id, market_account_id, statuses):
    result = await db.execute(
        select(MarketListingDraft).where(
            MarketListingDraft.source_product_id == source_product_id,
            MarketListingDraft.market_account_id == market_account_id,
            MarketListingDraft.draft_kind == "create",
            MarketListingDraft.status.in_(statuses),
        )
    )
    return result.scalar_one_or_none()


async def _load_submitting_create_draft(db, source_product_id, market_account_id):
    return await _load_create_draft_by_statuses(
        db,
        source_product_id,
        market_account_id,
        (SUBMITTING_DRAFT_STATUS,),
    )


async def _load_mutable_create_draft(db, source_product_id, market_account_id):
    return await _load_create_draft_by_statuses(
        db,
        source_product_id,
        market_account_id,
        MUTABLE_DRAFT_STATUSES,
    )


def _apply_adapter_result(draft: MarketListingDraft, snapshot: dict[str, Any], result) -> None:
    draft.source_product_version = snapshot["version"]
    draft.source_snapshot = snapshot
    draft.display_title = result.display_title
    draft.category_id = result.category_id
    draft.sale_price = result.sale_price
    draft.cost_price = result.cost_price
    draft.expected_profit = result.expected_profit
    draft.expected_margin_rate = result.expected_margin_rate
    draft.primary_image_url = result.primary_image_url
    draft.generated_payload = result.generated_payload
    draft.validation_result = result.validation_result
    draft.adapter_version = result.adapter_version
    draft.recipe_versions = result.recipe_versions
    draft.status = "needs_review"


async def _rollback_if_available(db) -> None:
    rollback = getattr(db, "rollback", None)
    if rollback is None:
        return
    try:
        await rollback()
    except Exception:
        # Keep original failures intact when rollback itself is unavailable/broken.
        return


async def _merge_if_available(db, entity):
    merge = getattr(db, "merge", None)
    if merge is None:
        return entity
    try:
        return await merge(entity)
    except Exception:
        # Keep flow working for fake DBs or sessions where merge is unavailable.
        return entity


def _apply_job_state(
    job,
    *,
    status: str,
    generated_source_version: str | None,
    error: dict[str, str] | None,
) -> None:
    job.status = status
    if generated_source_version is not None:
        job.generated_source_version = generated_source_version
    job.error = error
    if status == "completed":
        job.completed_at = datetime.now(timezone.utc)


async def _apply_generation_and_commit(
    job,
    db,
    snapshot: dict[str, Any],
    generated_source_version: str,
    source_product_id,
    draft_targets: list[DraftTarget],
) -> None:
    for target in draft_targets:
        submitting_draft = await _load_submitting_create_draft(
            db,
            source_product_id,
            target.market_account_id,
        )
        if submitting_draft is not None:
            continue

        draft = await _load_mutable_create_draft(
            db,
            source_product_id,
            target.market_account_id,
        )
        if (
            draft is not None
            and draft.source_product_version is not None
            and snapshot["version"] <= draft.source_product_version
        ):
            continue

        if draft is None:
            draft = MarketListingDraft(
                source_product_id=source_product_id,
                source_product_version=snapshot["version"],
                market_account_id=target.market_account_id,
                market_code=target.market_code,
                draft_kind="create",
                status="generated",
                source_snapshot=snapshot,
                generated_payload={},
                validation_result={"status": "valid"},
                recipe_versions={},
                adapter_version=target.result.adapter_version,
            )

        _apply_adapter_result(draft, snapshot, target.result)
        db.add(draft)

    _apply_job_state(
        job,
        status="completed",
        generated_source_version=generated_source_version,
        error=None,
    )
    await db.commit()


async def generate_drafts_for_job(job, db, processor_client, adapters=ADAPTERS):
    generated_source_version: str | None = None
    try:
        source_product_id = job.source_product_id
        user_id = job.user_id
        job.status = "processing"
        job.error = None

        snapshot = await processor_client.get_marketplace_snapshot(
            str(source_product_id),
            str(user_id),
        )
        generated_source_version = snapshot["version"]
        job.generated_source_version = generated_source_version

        accounts = await _load_connected_accounts(db, user_id)
        draft_targets: list[DraftTarget] = []
        for account in accounts:
            submitting_draft = await _load_submitting_create_draft(
                db,
                source_product_id,
                account.id,
            )
            if submitting_draft is not None:
                continue

            adapter = adapters.get(account.market_code)
            if adapter is None:
                continue

            settings_payload = _serialize_settings(account.settings)
            result = adapter.generate_draft(snapshot, settings_payload)
            draft_targets.append(
                DraftTarget(
                    market_account_id=account.id,
                    market_code=account.market_code,
                    result=result,
                )
            )

        try:
            await _apply_generation_and_commit(
                job,
                db,
                snapshot,
                generated_source_version,
                source_product_id,
                draft_targets,
            )
        except IntegrityError:
            await _rollback_if_available(db)
            job = await _merge_if_available(db, job)
            await _apply_generation_and_commit(
                job,
                db,
                snapshot,
                generated_source_version,
                source_product_id,
                draft_targets,
            )
    except Exception as exc:
        await _rollback_if_available(db)
        job = await _merge_if_available(db, job)
        _apply_job_state(
            job,
            status="failed",
            generated_source_version=generated_source_version,
            error={"type": exc.__class__.__name__, "message": str(exc)},
        )
        try:
            await db.commit()
        except Exception as commit_exc:
            raise exc from commit_exc
        raise
