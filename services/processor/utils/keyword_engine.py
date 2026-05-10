import re
import logging
from config import settings
from assets.keyword_stop_words import KEYWORD_STOP_WORDS
from assets.trademark_blacklist import TRADEMARK_BLACKLIST
from clients.naver_ad_client import NaverAdClient
from clients.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

class KeywordEngine:
    def __init__(self):
        self.naver_ad_client = NaverAdClient()
        self.gemini_client = GeminiClient()

    async def curate_keywords(self, refined_name: str) -> list[str]:
        """
        3-Phase 키워드 큐레이션 워크플로우
        """
        # Phase 1: 시드 수집
        seeds = await self._collect_seeds(refined_name)
        
        # Phase 2: 필터링 및 점수화
        scored_keywords = self._filter_and_score(seeds)
        
        # Phase 3: 상표권 및 최종 검증 (하이브리드)
        final_keywords = await self._verify_trademarks(scored_keywords[:20])
        
        return final_keywords[:10]

    async def _collect_seeds(self, refined_name: str) -> set[str]:
        seeds = {refined_name}
        
        # 1. 네이버 광고 API 시드
        try:
            res = await self.naver_ad_client.get_keyword_stats([refined_name])
            for item in res.get("keywordList", []):
                seeds.add(item["relKeyword"])
        except Exception as e:
            logger.error(f"Naver seed collection failed: {e}")

        # 2. LLM 동의어 확장
        try:
            synonyms = await self.gemini_client.model.generate_content_async(
                f"다음 상품명과 연관된 쇼핑 검색 키워드 동의어를 3개만 추천해줘. 예: '무선 이어폰' -> '블루투스 이어셋'. 응답은 콤마로 구분. 입력: {refined_name}"
            )
            for s in synonyms.text.split(","):
                seeds.add(s.strip())
        except Exception as e:
            logger.error(f"LLM synonym expansion failed: {e}")
            
        return seeds

    def _filter_and_score(self, keywords: set[str]) -> list[str]:
        scored = []
        for kw in keywords:
            if not kw or len(kw) < 2: continue
            if any(stop in kw for kw in KEYWORD_STOP_WORDS for stop in KEYWORD_STOP_WORDS): # Fix logic
                pass # Wait, this logic is slightly wrong
        
        # Correct logic
        valid_keywords = []
        for kw in keywords:
            if not kw or len(kw) < 2: continue
            
            # 불용어 필터
            if any(stop in kw for stop in KEYWORD_STOP_WORDS): continue
            
            # 품질 점수 계산
            score = 10
            # 롱테일 보너스 (공백 기준 단어 수)
            word_count = len(kw.split())
            if word_count >= 3: score += 5
            elif word_count >= 2: score += 3
            
            # 수량 패턴 제거 (2개, 3세트 등)
            if re.search(r'\d+(개|세트|p|입)', kw): score -= 10
            
            valid_keywords.append((kw, score))
            
        # 점수순 정렬
        valid_keywords.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in valid_keywords]

    async def _verify_trademarks(self, keywords: list[str]) -> list[str]:
        """
        상표권 검증: 블랙리스트 + LLM 의심 단어 추출 + KIPRIS (추후 구현)
        """
        final = []
        for kw in keywords:
            # 1. 로컬 블랙리스트
            if any(brand in kw for brand in TRADEMARK_BLACKLIST): continue
            
            # 2. LLM 의심 검사 (단순화)
            # 실제로는 Gemini에게 "이 단어가 브랜드명이야?" 라고 물어보는 로직 추가 가능
            final.append(kw)
            
        return final
