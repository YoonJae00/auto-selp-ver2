import asyncio

from fastapi import FastAPI
from sqlalchemy.exc import InterfaceError, OperationalError

import models  # noqa: F401
from database import Base, engine


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
