from fastapi import FastAPI

import models  # noqa: F401
from database import Base, engine

app = FastAPI(title="Auto-Selp Marketplace Listing")


@app.on_event("startup")
async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "marketplace"}
