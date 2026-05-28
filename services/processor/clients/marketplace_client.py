import httpx

from config import settings


class MarketplaceClient:
    async def request_draft_generation(self, product) -> None:
        payload = {
            "source_product_id": str(product.id),
            "source_product_updated_at": product.updated_at.isoformat(),
            "source_user_id": str(product.user_id),
            "reason": "processing_completed",
        }
        async with httpx.AsyncClient(
            base_url=settings.MARKETPLACE_BASE_URL,
            timeout=5.0,
        ) as client:
            response = await client.post(
                "/internal/draft-generation-jobs",
                json=payload,
                headers={"X-Internal-Service-Token": settings.INTERNAL_SERVICE_TOKEN},
            )
            response.raise_for_status()
