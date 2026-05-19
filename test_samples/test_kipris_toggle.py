import sys
import os
import asyncio
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../services/processor')))

# 환경변수 로드
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

from utils.keyword_engine import KeywordEngine
from clients.gemini_client import GeminiClient

async def main():
    print("=== KIPRIS 토글 통합 테스트 ===")

    llm_client = GeminiClient()
    
    # KIPRIS OFF 상태 테스트
    print("\n--- [TEST 1] KIPRIS OFF 상태 (kipris_enabled=False) ---")
    engine_off = KeywordEngine(llm_client, kipris_enabled=False)
    
    test_keywords = ["가스 쇼바", "3BOSS", "다이슨", "무보링 댐퍼"]
    print(f"테스트 키워드: {test_keywords}")
    
    safe_off, warnings_off = await engine_off._verify_trademarks(test_keywords)
    
    print(f"안전한 키워드: {safe_off}")
    print(f"경고 수: {len(warnings_off)}")
    for w in warnings_off:
        print(f"  - [{w['type']}] {w['keyword']}: {w.get('reason')}")
        assert w['type'] == 'llm_suspected', "KIPRIS OFF 상태에서는 llm_suspected 타입만 나와야 합니다."
        
    assert "다이슨" not in safe_off, "블랙리스트인 '다이슨'은 제거되어야 합니다."
    assert "가스 쇼바" in safe_off, "일반명사 '가스 쇼바'는 안전해야 합니다."


    # KIPRIS ON 상태 테스트
    print("\n--- [TEST 2] KIPRIS ON 상태 (kipris_enabled=True) ---")
    engine_on = KeywordEngine(llm_client, kipris_enabled=True)
    
    safe_on, warnings_on = await engine_on._verify_trademarks(test_keywords)
    
    print(f"안전한 키워드: {safe_on}")
    print(f"경고 수: {len(warnings_on)}")
    for w in warnings_on:
        print(f"  - [{w['type']}] {w['keyword']}")
        assert w['type'] == 'kipris_confirmed', "KIPRIS ON 상태에서는 kipris_confirmed 타입이 나와야 합니다."
        
    print("\n✅ 모든 테스트 통과!")

if __name__ == "__main__":
    asyncio.run(main())
