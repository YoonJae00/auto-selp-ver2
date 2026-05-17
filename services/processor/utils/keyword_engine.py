import re
import logging
from config import settings
from assets.keyword_stop_words import KEYWORD_STOP_WORDS
from assets.trademark_blacklist import TRADEMARK_BLACKLIST
from clients.naver_ad_client import NaverAdClient
from clients.llm_client import LLMClient
from clients.kipris_client import KiprisClient

logger = logging.getLogger(__name__)

class KeywordEngine:
    def __init__(self, llm_client: LLMClient):
        self.naver_ad_client = NaverAdClient()
        self.llm_client = llm_client
        self.kipris_client = KiprisClient()

    async def curate_keywords(self, refined_name: str) -> tuple[list[str], list[dict]]:
        """
        3-Phase 키워드 큐레이션 워크플로우
        반환값: (safe_keywords, warnings)
        """
        # Phase 1: 시드 수집
        seeds = await self._collect_seeds(refined_name)
        
        # Phase 2: 필터링 및 점수화
        scored_keywords = self._filter_and_score(seeds)
        
        # Phase 3: 상표권 및 최종 검증 (하이브리드)
        safe_keywords, warnings = await self._verify_trademarks(scored_keywords[:20])
        
        return safe_keywords[:10], warnings

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
            synonyms = await self.llm_client.get_synonyms(refined_name)
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

    async def _verify_trademarks(self, keywords: list[str]) -> tuple[list[str], list[dict]]:
        """
        상표권 검증: 블랙리스트 + KIPRIS 실시간 검색
        """
        safe = []
        warnings = []
        
        for kw in keywords:
            # 1. 로컬 블랙리스트 (완전 제외)
            if any(brand in kw for brand in TRADEMARK_BLACKLIST):
                continue
            
            # 2. KIPRIS 실시간 검증
            try:
                res = await self.kipris_client.search_trademark(kw)
                if res.get("exists"):
                    warnings.append({
                        "keyword": kw,
                        "info": res
                    })
                else:
                    safe.append(kw)
            except Exception as e:
                logger.error(f"KIPRIS verification failed for {kw}: {e}")
                # 에러 발생 시 안전하게 safe에 추가 (또는 warning 처리)
                safe.append(kw)
            
        return safe, warnings
