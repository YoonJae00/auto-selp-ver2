import asyncio
import uuid

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

import models  # noqa: F401
from auth import get_current_user, require_internal_service_token
from database import Base, engine
from database import get_db
from models import (
    MarketAccount,
    MarketAccountSettings,
    MarketDraftGenerationJob,
    MarketListingDraft,
    MarketSubmissionAttempt,
    MarketSubmissionJob,
)
from schemas import (
    DraftGenerationJobResponse,
    DraftGenerationRequest,
    MarketAccountCreate,
    MarketAccountResponse,
    MarketAccountSettingsResponse,
    MarketAccountSettingsUpdate,
    MarketListingDraftUpdate,
    MarketListingDraftListResponse,
    MarketListingDraftResponse,
    SubmissionCreate,
    SubmissionJobListResponse,
    SubmissionJobResponse,
)
from security import encrypt_credentials
from tasks import generate_market_listing_drafts

app = FastAPI(title="Auto-Selp Marketplace Listing")

DB_STARTUP_MAX_ATTEMPTS = 5
DB_STARTUP_RETRY_DELAY_SECONDS = 2.0
DB_STARTUP_TRANSIENT_ERRORS = (
    ConnectionError,
    OSError,
    TimeoutError,
    InterfaceError,
    OperationalError,
)


@app.on_event("startup")
async def create_tables() -> None:
    for attempt in range(1, DB_STARTUP_MAX_ATTEMPTS + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except DB_STARTUP_TRANSIENT_ERRORS:
            if attempt == DB_STARTUP_MAX_ATTEMPTS:
                raise
            await asyncio.sleep(DB_STARTUP_RETRY_DELAY_SECONDS)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "marketplace"}


@app.post("/accounts", response_model=MarketAccountResponse)
async def create_market_account(
    account: MarketAccountCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    new_account = MarketAccount(
        id=uuid.uuid4(),
        user_id=current_user["id"],
        market_code=account.market_code,
        display_name=account.display_name,
        credentials_encrypted=encrypt_credentials(account.credentials),
    )
    db.add(new_account)
    await db.commit()
    await db.refresh(new_account)
    return new_account


@app.get("/accounts", response_model=list[MarketAccountResponse])
async def list_market_accounts(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MarketAccount)
        .where(MarketAccount.user_id == current_user["id"])
        .order_by(MarketAccount.created_at.desc())
    )
    return result.scalars().all()


@app.put("/accounts/{account_id}/settings", response_model=MarketAccountSettingsResponse)
async def update_market_account_settings(
    account_id: uuid.UUID,
    settings_update: MarketAccountSettingsUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account_result = await db.execute(
        select(MarketAccount).where(
            and_(
                MarketAccount.id == account_id,
                MarketAccount.user_id == current_user["id"],
            )
        )
    )
    account = account_result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Market account not found")

    settings_result = await db.execute(
        select(MarketAccountSettings).where(
            MarketAccountSettings.market_account_id == account_id
        )
    )
    existing_settings = settings_result.scalar_one_or_none()
    if existing_settings is None:
        existing_settings = MarketAccountSettings(
            id=uuid.uuid4(),
            market_account_id=account_id,
            **settings_update.model_dump(),
        )
        db.add(existing_settings)
    else:
        for field, value in settings_update.model_dump(exclude_unset=True).items():
            setattr(existing_settings, field, value)

    await db.commit()
    await db.refresh(existing_settings)
    return existing_settings


@app.get("/accounts/{account_id}/settings", response_model=MarketAccountSettingsResponse)
async def get_market_account_settings(
    account_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account_result = await db.execute(
        select(MarketAccount).where(
            MarketAccount.id == account_id,
            MarketAccount.user_id == current_user["id"],
        )
    )
    account = account_result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Market account not found")

    settings_result = await db.execute(
        select(MarketAccountSettings).where(
            MarketAccountSettings.market_account_id == account_id
        )
    )
    existing_settings = settings_result.scalar_one_or_none()
    if existing_settings is None:
        raise HTTPException(status_code=404, detail="Market account settings not found")
    return existing_settings


@app.post(
    "/internal/draft-generation-jobs",
    response_model=DraftGenerationJobResponse,
    status_code=202,
    dependencies=[Depends(require_internal_service_token)],
)
async def create_draft_generation_job(
    payload: DraftGenerationRequest,
    db: AsyncSession = Depends(get_db),
):
    job = MarketDraftGenerationJob(
        id=uuid.uuid4(),
        user_id=payload.source_user_id,
        source_product_id=payload.source_product_id,
        requested_source_version=payload.source_product_updated_at.isoformat(),
        reason=payload.reason,
        status="queued",
        error=None,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    generate_market_listing_drafts.delay(str(job.id))
    return job


@app.get("/drafts", response_model=MarketListingDraftListResponse)
async def list_drafts(
    market_code: str | None = None,
    status: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(MarketListingDraft)
        .join(MarketAccount, MarketListingDraft.market_account_id == MarketAccount.id)
        .where(MarketAccount.user_id == current_user["id"])
    )

    if market_code is not None:
        stmt = stmt.where(MarketListingDraft.market_code == market_code)
    if status is not None:
        stmt = stmt.where(MarketListingDraft.status == status)

    stmt = stmt.order_by(MarketListingDraft.updated_at.desc())
    result = await db.execute(stmt)
    return {"items": result.scalars().all()}


@app.get("/drafts/{draft_id}", response_model=MarketListingDraftResponse)
async def get_draft(
    draft_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MarketListingDraft)
        .join(MarketAccount, MarketListingDraft.market_account_id == MarketAccount.id)
        .where(
            MarketListingDraft.id == draft_id,
            MarketAccount.user_id == current_user["id"],
        )
    )
    draft = result.scalar_one_or_none()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@app.patch("/drafts/{draft_id}", response_model=MarketListingDraftResponse)
async def update_draft(
    draft_id: uuid.UUID,
    payload: MarketListingDraftUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MarketListingDraft)
        .join(MarketAccount, MarketListingDraft.market_account_id == MarketAccount.id)
        .where(
            MarketListingDraft.id == draft_id,
            MarketAccount.user_id == current_user["id"],
        )
    )
    draft = result.scalar_one_or_none()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    if payload.status is not None:
        if payload.status not in {"generated", "needs_review", "ready", "failed"}:
            raise HTTPException(status_code=422, detail="Unsupported draft status")
        if payload.status == "ready" and _validation_status(draft) == "blocked":
            raise HTTPException(status_code=422, detail="blocked draft cannot be marked ready")
        draft.status = payload.status

    if payload.override_patch is not None:
        draft.override_patch = payload.override_patch

    await db.commit()
    await db.refresh(draft)
    return draft


@app.post("/submissions", response_model=SubmissionJobResponse, status_code=202)
async def create_submission(
    payload: SubmissionCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not payload.draft_ids:
        raise HTTPException(status_code=422, detail="draft_ids is required")

    account_result = await db.execute(
        select(MarketAccount).where(
            MarketAccount.id == payload.market_account_id,
            MarketAccount.user_id == current_user["id"],
        )
    )
    account = account_result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Market account not found")

    drafts_result = await db.execute(
        select(MarketListingDraft).where(
            MarketListingDraft.market_account_id == account.id,
            MarketListingDraft.id.in_(payload.draft_ids),
        )
    )
    drafts = drafts_result.scalars().all()
    if len(drafts) != len(set(payload.draft_ids)):
        raise HTTPException(status_code=404, detail="One or more drafts were not found")

    blocked_drafts = [draft for draft in drafts if _validation_status(draft) == "blocked"]
    if blocked_drafts:
        raise HTTPException(status_code=422, detail="blocked drafts cannot be submitted")

    invalid_statuses = [
        draft.status for draft in drafts if draft.status not in {"ready", "needs_review", "generated"}
    ]
    if invalid_statuses:
        raise HTTPException(status_code=422, detail="draft status cannot be submitted")

    job = MarketSubmissionJob(
        id=uuid.uuid4(),
        user_id=current_user["id"],
        market_account_id=account.id,
        market_code=account.market_code,
        draft_ids=[str(draft_id) for draft_id in payload.draft_ids],
        status="queued",
        draft_count=len(drafts),
        error=None,
    )
    db.add(job)

    for draft in drafts:
        draft.status = "submitting"
        attempt = MarketSubmissionAttempt(
            id=uuid.uuid4(),
            submission_job_id=job.id,
            draft_id=draft.id,
            market_code=draft.market_code,
            status="queued",
            attempt_number=1,
            submitted_payload=_effective_payload(draft),
            response_payload=None,
            error=None,
        )
        db.add(attempt)

    await db.commit()
    await db.refresh(job)
    return job


@app.get("/submissions", response_model=SubmissionJobListResponse)
async def list_submissions(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MarketSubmissionJob)
        .where(MarketSubmissionJob.user_id == current_user["id"])
        .order_by(MarketSubmissionJob.created_at.desc())
    )
    return {"items": result.scalars().all()}


def _validation_status(draft: MarketListingDraft) -> str | None:
    validation_result = draft.validation_result
    if isinstance(validation_result, dict):
        status = validation_result.get("status")
        if isinstance(status, str):
            return status
    return None


def _effective_payload(draft: MarketListingDraft) -> dict:
    payload = dict(draft.generated_payload or {})
    if isinstance(draft.override_patch, dict):
        payload = _deep_merge(payload, draft.override_patch)
    return payload


def _deep_merge(base: dict, patch: dict) -> dict:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
