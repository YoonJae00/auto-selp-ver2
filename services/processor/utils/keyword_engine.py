import re
import logging
from config import settings
from assets.keyword_stop_words import KEYWORD_STOP_WORDS
from assets.trademark_blacklist import TRADEMARK_BLACKLIST
from clients.naver_ad_client import NaverAdClient
from clients.llm_base import LLMClient

logger = logging.getLogger(__name__)

class KeywordEngine:
    def __init__(self, llm_client: LLMClient):
        self.naver_ad_client = NaverAdClient()
        self.llm_client = llm_client

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
            synonyms = await self.llm_client.generate_synonyms(refined_name)
            for s in synonyms:
                seeds.add(s)
        except Exception as e:
            logger.error(f"LLM synonym expansion failed: {e}")
            
        return seeds

    def _filter_and_score(self, keywords: set[str]) -> list[str]:
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
        상표권 검증: 블랙리스트 + LLM 의심 단어 추출 + KIPRIS
        """
        final = []
        for kw in keywords:
            # 1. 로컬 블랙리스트
            if any(brand in kw for brand in TRADEMARK_BLACKLIST): continue
            
            # 2. LLM 의심 검사
            is_trademark = await self.llm_client.verify_trademark(kw)
            if is_trademark:
                # 3. KIPRIS MCP 정밀 검증 (상표권 의심 시에만 호출 가능하도록 구조화)
                # mcp_client = KiprisClient()
                # if await mcp_client.check_trademark(kw): continue
                continue
            
            final.append(kw)
            
        return final
