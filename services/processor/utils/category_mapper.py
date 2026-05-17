import pandas as pd
import logging
from config import settings
from clients.naver_search_client import NaverSearchClient
from clients.coupang_client import CoupangClient

logger = logging.getLogger(__name__)

class CategoryMapper:
    def __init__(self):
        self.naver_search_client = NaverSearchClient()
        self.coupang_client = CoupangClient()
        self.mapping_file = "assets/naver_category_mapping.xls"
        self._df = None

    def _load_mapping(self):
        if self._df is None:
            try:
                # Naver mapping file: ['카테고리번호', '대분류', '중분류', '소분류', '세분류']
                self._df = pd.read_excel(self.mapping_file)
                # Fill NaN with empty string for path joining
                temp_df = self._df.fillna("")
                self._df['category_path'] = temp_df.apply(
                    lambda x: f"{x['대분류']}>{x['중분류']}>{x['소분류']}>{x['세분류']}".strip(">"), axis=1
                )
            except Exception as e:
                logger.error(f"Failed to load Naver category mapping: {e}")
                self._df = pd.DataFrame()

    async def get_naver_category(self, product_name: str) -> dict:
        """
        네이버 카테고리 매칭: API 검색 -> 로컬 매핑 -> 부분 일치
        """
        try:
            # 1. API 검색
            res = await self.naver_search_client.search_shop(product_name)
            items = res.get("items", [])
            if not items: return {"path": "", "id": ""}
            
            item = items[0]
            # Construct path from API response
            api_path = f"{item['category1']}>{item['category2']}>{item['category3']}>{item['category4']}".strip(">")
            
            # 2. 로컬 매핑 (완전 일치)
            self._load_mapping()
            
            if 'category_path' in self._df.columns:
                match = self._df[self._df['category_path'] == api_path]
                if not match.empty:
                    return {"path": api_path, "id": str(match.iloc[0]['카테고리번호'])}
                
                # 3. 부분 일치 (세분류 기준)
                last_cat = item.get('category4') or item.get('category3')
                if last_cat:
                    partial_match = self._df[self._df['category_path'].str.contains(last_cat, na=False)]
                    if not partial_match.empty:
                        return {"path": partial_match.iloc[0]['category_path'], "id": str(partial_match.iloc[0]['카테고리번호'])}
            
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
