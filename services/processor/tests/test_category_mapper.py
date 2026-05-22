import os

import pytest

os.environ.setdefault("NAVER_CLIENT_ID", "test")
os.environ.setdefault("NAVER_CLIENT_SECRET", "test")
os.environ.setdefault("Coupang_Access_Key", "test")
os.environ.setdefault("Coupang_Secret_Key", "test")

from utils.category_mapper import CategoryMapper, normalize_naver_category_path


def reset_naver_mapping_cache():
    CategoryMapper._naver_path_to_id = None


def test_normalize_naver_category_path_removes_prefix_and_empty_parts():
    assert (
        normalize_naver_category_path("네이버: 출산/육아 > 완구/인형 >  > 쿠킹토이 ")
        == "출산/육아>완구/인형>쿠킹토이"
    )
    assert (
        normalize_naver_category_path("naver: 출산/육아>완구/인형>역할놀이/소꿉놀이>쿠킹토이")
        == "출산/육아>완구/인형>역할놀이/소꿉놀이>쿠킹토이"
    )


def test_get_naver_category_code_uses_static_json_asset():
    reset_naver_mapping_cache()
    mapper = CategoryMapper()

    assert (
        mapper.get_naver_category_code("네이버: 출산/육아>완구/인형>역할놀이/소꿉놀이>쿠킹토이")
        == "50004447"
    )
    assert len(CategoryMapper._naver_path_to_id) == 4993


@pytest.mark.asyncio
async def test_get_naver_category_maps_api_path_to_code():
    reset_naver_mapping_cache()
    mapper = CategoryMapper()

    class FakeNaverSearchClient:
        async def search_shop(self, _product_name):
            return {
                "items": [
                    {
                        "category1": "출산/육아",
                        "category2": "완구/인형",
                        "category3": "역할놀이/소꿉놀이",
                        "category4": "쿠킹토이",
                    }
                ]
            }

    mapper.naver_search_client = FakeNaverSearchClient()

    assert await mapper.get_naver_category("쿠킹토이") == {
        "path": "출산/육아>완구/인형>역할놀이/소꿉놀이>쿠킹토이",
        "id": "50004447",
    }
