import asyncio
import uuid

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

import models  # noqa: F401
from auth import get_current_user
from database import Base, engine
from database import get_db
from models import MarketAccount, MarketAccountSettings
from schemas import (
    MarketAccountCreate,
    MarketAccountResponse,
    MarketAccountSettingsResponse,
    MarketAccountSettingsUpdate,
)
from security import encrypt_credentials


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
