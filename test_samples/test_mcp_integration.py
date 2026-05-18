"""
keyword_engine 하이브리드 파이프라인 통합 테스트
- LLM 배치 브랜드 분류 → brand_suspected만 KIPRIS 검증
"""
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
    print("=== 하이브리드 상표권 파이프라인 통합 테스트 ===\n")

    df = pd.read_excel(os.path.join(os.path.dirname(__file__), 'doto_sample.xlsx'))
    product_names = df['상품명'].head(5).tolist()

    llm_client = GeminiClient()
    engine = KeywordEngine(llm_client)

    total_kipris_calls = 0

    for i, name in enumerate(product_names, 1):
        print(f"[{i}/5] 상품명: {name}")

        # Phase 1: 시드 수집 (Naver Ad API + LLM 동의어)
        seeds = await engine._collect_seeds(name)
        print(f"  시드 수집: {len(seeds)}개")

        # Phase 2: 필터링
        scored = engine._filter_and_score(seeds)
        top20 = scored[:20]
        print(f"  필터 후: {len(top20)}개")

        # Phase 3: 하이브리드 상표권 검증
        # LLM 브랜드 분류 먼저
        classification = await llm_client.classify_brand_keywords(top20)
        brand_suspected = classification.get("brand_suspected", [])
        generic = classification.get("generic", [])

        print(f"  LLM 분류 → generic: {len(generic)}개 (KIPRIS 스킵), brand_suspected: {len(brand_suspected)}개 (KIPRIS 검증)")
        if brand_suspected:
            print(f"  브랜드 의심 키워드: {brand_suspected}")

        total_kipris_calls += len(brand_suspected)

        # 최종 검증
        safe_keywords, warnings = await engine._verify_trademarks(top20)
        print(f"  최종 안전 키워드: {len(safe_keywords)}개")
        if warnings:
            print(f"  ⚠️  상표 경고: {[w['keyword'] for w in warnings]}")
        print()

    print(f"=== 요약 ===")
    print(f"상품 5개 처리 시 총 KIPRIS 호출 수: {total_kipris_calls}회")
    print(f"기존 방식 예상 KIPRIS 호출 수: {5 * 20}회 (상품당 최대 20회)")
    if total_kipris_calls < 5 * 20:
        saved = 5 * 20 - total_kipris_calls
        reduction = (saved / (5 * 20)) * 100
        print(f"절감 효과: {saved}회 절약 ({reduction:.0f}% 감소) ✅")
    print(f"\n월 10,000개 기준 KIPRIS 예상 호출:")
    avg_per_product = total_kipris_calls / 5
    print(f"  기존: {10000 * 20:,}회 (월 한도 200배 초과)")
    print(f"  신규: 약 {int(10000 * avg_per_product):,}회 (avg {avg_per_product:.1f}회/상품)")

if __name__ == "__main__":
    asyncio.run(main())
