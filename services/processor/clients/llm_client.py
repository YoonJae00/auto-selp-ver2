from abc import ABC, abstractmethod

class LLMClient(ABC):
    @abstractmethod
    async def refine_product_name(self, original_name: str) -> str:
        pass

    @abstractmethod
    async def get_synonyms(self, refined_name: str) -> list[str]:
        pass

    @abstractmethod
    async def classify_brand_keywords(self, keywords: list[str]) -> dict:
        """
        키워드 목록을 한 번에 분류:
        - brand_suspected: 고유 브랜드/상표 의심 → KIPRIS 검증 필요
        - generic: 일반 명사 → 안전 (KIPRIS 스킵)
        반환: {"brand_suspected": [...], "generic": [...]}
        """
        pass

    @abstractmethod
    async def extract_product_attributes(self, refined_name: str, image_urls: list[str], attributes: list) -> dict:
        """
        상세 이미지로부터 카테고리 속성 추출
        """
        pass
