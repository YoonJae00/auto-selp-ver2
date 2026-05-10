import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import Prompt
from config import settings

class PromptManager:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def get_prompt(self, key: str, default: str) -> str:
        # 1. Try Redis cache
        try:
            cached = await self.redis.get(f"prompt:{key}")
            if cached:
                return cached
        except Exception:
            pass

        # 2. Try DB
        result = await self.db.execute(select(Prompt).where(Prompt.key == key))
        prompt_record = result.scalar_one_or_none()
        
        if prompt_record:
            # Cache for 1 hour
            try:
                await self.redis.set(f"prompt:{key}", prompt_record.template, ex=3600)
            except Exception:
                pass
            return prompt_record.template
            
        # 3. Fallback to default
        return default

    async def clear_cache(self, key: str):
        try:
            await self.redis.delete(f"prompt:{key}")
        except Exception:
            pass
