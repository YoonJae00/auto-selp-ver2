import httpx

from config import settings


class ProcessorClient:
    async def get_marketplace_snapshot(self, product_id: str, user_id: str) -> dict:
        async with httpx.AsyncClient(
            base_url=settings.PROCESSOR_BASE_URL,
            timeout=10.0,
        ) as client:
            response = await client.get(
                f"/internal/products/{product_id}/marketplace-snapshot",
                params={"user_id": user_id},
                headers={"X-Internal-Service-Token": settings.INTERNAL_SERVICE_TOKEN},
            )
            response.raise_for_status()
            return response.json()
