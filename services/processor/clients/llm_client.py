from abc import ABC, abstractmethod
import json


def smartstore_name_prompt(
    refined_name: str,
    keywords: list[str],
    brand_name: str | None,
    category_path: str | None,
) -> str:
    context = json.dumps(
        {"refined_name": refined_name, "verified_keywords": keywords, "excluded_brand": brand_name, "category_path": category_path},
        ensure_ascii=False,
    )
    return f"""스마트스토어 검색용 상품명 후보를 정확히 3개 만들고 JSON {{"candidates": ["...", "...", "..."]}}만 응답하세요.
검증된 키워드와 정제 상품명에 실제로 포함된 단어만 사용하세요. 새 기능, 소재, 수량, 브랜드를 추측하거나 창작하지 마세요.
완성형 키워드의 단어 순서와 인접성을 유지하고, 목록 앞쪽의 우선 키워드를 상품명 앞쪽에 배치하며 겹침 사슬을 활용하세요.
각 후보는 25~35자를 목표로 하되 반드시 50자 이하, 최대 9단어, 동일 단어 최대 2회로 제한하세요.
특수문자, 홍보 문구, 최상급 표현을 사용하지 마세요.
입력: {context}"""

class LLMClient(ABC):
    @abstractmethod
    async def generate_smartstore_name_candidates(
        self,
        refined_name: str,
        keywords: list[str],
        brand_name: str | None = None,
        category_path: str | None = None,
    ) -> list[str]:
        pass

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
