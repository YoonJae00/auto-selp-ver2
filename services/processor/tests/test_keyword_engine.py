import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from utils.keyword_engine import KeywordEngine

@pytest.mark.asyncio
async def test_keyword_engine_curation():
    with patch("clients.naver_ad_client.NaverAdClient.get_keyword_stats") as mock_naver, \
         patch("google.generativeai.GenerativeModel.generate_content_async") as mock_gemini:
        
        mock_naver.return_value = {"keywordList": [{"relKeyword": "연관키워드1"}, {"relKeyword": "연관키워드2"}]}
        
        mock_response = MagicMock()
        mock_response.text = "동의어1, 동의어2"
        mock_gemini.return_value = mock_response
        
        engine = KeywordEngine()
        keywords = await engine.curate_keywords("테스트 상품")
        
        assert len(keywords) > 0
        # "테스트 상품" (original) + 네이버 연관어 + LLM 동의어 중 상위 10개
        assert any(k in keywords for k in ["테스트 상품", "연관키워드1", "동의어1"])
