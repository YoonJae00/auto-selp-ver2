import json
import logging
import re
from pathlib import Path
from clients.naver_search_client import NaverSearchClient
from clients.coupang_client import CoupangClient

logger = logging.getLogger(__name__)


NAVER_CATEGORY_PREFIX_RE = re.compile(r"^\s*(?:네이버|naver)\s*:\s*", re.IGNORECASE)


def normalize_naver_category_path(category_path: str) -> str:
    category_path = NAVER_CATEGORY_PREFIX_RE.sub("", str(category_path or ""))
    return ">".join(part.strip() for part in category_path.split(">") if part.strip())


class CategoryMapper:
    _naver_path_to_id = None

    def __init__(self):
        self.naver_search_client = NaverSearchClient()
        self.coupang_client = CoupangClient()
        self.mapping_file = Path(__file__).resolve().parent.parent / "assets" / "naver_category_mapping.json"

    def _load_mapping(self):
        if CategoryMapper._naver_path_to_id is None:
            try:
                with self.mapping_file.open(encoding="utf-8") as f:
                    raw_mapping = json.load(f)
                CategoryMapper._naver_path_to_id = {
                    normalize_naver_category_path(path): str(category_id)
                    for path, category_id in raw_mapping.items()
                }
            except Exception as e:
                logger.error(f"Failed to load Naver category mapping: {e}")
                CategoryMapper._naver_path_to_id = {}

    def get_naver_category_code(self, category_path: str) -> str:
        self._load_mapping()
        normalized_path = normalize_naver_category_path(category_path)
        return CategoryMapper._naver_path_to_id.get(normalized_path, "")

    async def get_naver_category(self, product_name: str) -> dict:
        """
        네이버 카테고리 매칭: API 검색 -> 로컬 JSON 매핑 -> 부분 일치
        """
        try:
            # 1. API 검색
            res = await self.naver_search_client.search_shop(product_name)
            items = res.get("items", [])
            if not items: return {"path": "", "id": ""}
            
            item = items[0]
            # Construct path from API response
            api_path = normalize_naver_category_path(
                ">".join(
                    [
                        item.get("category1", ""),
                        item.get("category2", ""),
                        item.get("category3", ""),
                        item.get("category4", ""),
                    ]
                )
            )
            
            # 2. 로컬 매핑 (완전 일치)
            self._load_mapping()

            category_id = CategoryMapper._naver_path_to_id.get(api_path, "")
            if category_id:
                return {"path": api_path, "id": category_id}
                
            # 3. 부분 일치 (세분류 기준)
            last_cat = item.get('category4') or item.get('category3')
            if last_cat:
                normalized_last_cat = normalize_naver_category_path(last_cat)
                for path, mapped_id in CategoryMapper._naver_path_to_id.items():
                    if normalized_last_cat in path:
                        return {"path": path, "id": mapped_id}
            
            return {"path": api_path, "id": "Manual Check"}
        except Exception as e:
            logger.error(f"Naver category mapping failed: {e}")
            return {"path": "Error", "id": ""}

    async def get_coupang_category(self, product_name: str, brand: str = "") -> str:
        """
        쿠팡 카테고리 매칭 (Predict API)
        """
        try:
            res = await self.coupang_client.predict_category(product_name, brand)
            if res.get("data") and res["data"].get("predictedCategoryId"):
                return str(res["data"]["predictedCategoryId"])
            return "Manual Check"
        except Exception as e:
            logger.error(f"Coupang category prediction failed: {e}")
            return "Error"
