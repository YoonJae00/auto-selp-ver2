import asyncio
import uuid

from sqlalchemy import select

from celery_app import celery_app
from clients.processor_client import ProcessorClient
from database import SessionLocal
from models import MarketDraftGenerationJob
from services.draft_generation import generate_drafts_for_job


@celery_app.task(name="generate_market_listing_drafts")
def generate_market_listing_drafts(job_id: str):
    return asyncio.run(_run_generation_job(job_id))


async def _run_generation_job(job_id: str):
    async with SessionLocal() as db:
        result = await db.execute(
            select(MarketDraftGenerationJob).where(
                MarketDraftGenerationJob.id == uuid.UUID(job_id)
            )
        )
        job = result.scalar_one()
        await generate_drafts_for_job(job, db, ProcessorClient())
        return {"job_id": job_id, "status": job.status}


__all__ = ["celery_app", "generate_market_listing_drafts"]
