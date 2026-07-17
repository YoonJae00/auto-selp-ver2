import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from utils.keyword_engine import KeywordEngine

@pytest.fixture
def mock_llm():
    client = MagicMock()
    client.get_synonyms = AsyncMock(return_value=["동의어1", "동의어2"])
    async def mock_classify(keywords):
        brand_suspected = [kw for kw in keywords if kw == "동의어1"]
        generic = [kw for kw in keywords if kw != "동의어1"]
        return {"brand_suspected": brand_suspected, "generic": generic}
    client.classify_brand_keywords = AsyncMock(side_effect=mock_classify)
    return client

@pytest.mark.asyncio
async def test_keyword_engine_curation_returns_warnings(mock_llm):
    with patch("clients.naver_ad_client.NaverAdClient.get_keyword_stats") as mock_naver:
        mock_naver.return_value = {"keywordList": [{"relKeyword": "연관키워드1"}]}
        
        engine = KeywordEngine(mock_llm)
        # curate_keywords가 (safe_keywords, warnings) 튜플을 반환해야 함
        safe, warnings = await engine.curate_keywords("테스트 상품")
        
        assert isinstance(safe, list)
        assert isinstance(warnings, list)
        
        # "동의어1"은 warnings에 있어야 함
        warning_keywords = [w["keyword"] for w in warnings]
        assert "동의어1" in warning_keywords
        assert any(w["keyword"] == "동의어1" and w["type"] == "llm_suspected" for w in warnings)
        
        # "테스트 상품", "연관키워드1" 등은 safe에 있어야 함
        assert "테스트 상품" in safe
        assert "연관키워드1" in safe
        assert "동의어1" not in safe

@pytest.mark.asyncio
async def test_keyword_engine_trademark_blacklist(mock_llm):
    with patch("utils.keyword_engine.TRADEMARK_BLACKLIST", ["블랙리스트"]), \
         patch("clients.naver_ad_client.NaverAdClient.get_keyword_stats") as mock_naver:
        mock_naver.return_value = {"keywordList": [{"relKeyword": "블랙리스트 키워드"}]}
        
        engine = KeywordEngine(mock_llm)
        safe, warnings = await engine.curate_keywords("테스트")
        
        # 로컬 블랙리스트에 걸리면 아예 결과에서 빠져야 함 (기존 로직 유지)
        assert "블랙리스트 키워드" not in safe
        assert not any(w["keyword"] == "블랙리스트 키워드" for w in warnings)
