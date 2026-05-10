import httpx
import json
import logging
from config import settings
from utils.backoff import retry_with_backoff
from clients.llm_base import LLMClient

logger = logging.getLogger(__name__)

class OpenAIClient(LLMClient):
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        # 최신 모델 gpt-5-nano (PRD 명시) 또는 gpt-4o-mini 사용
        self.model = "gpt-5-nano" 
        self.base_url = "https://api.openai.com/v1/chat/completions"

    @retry_with_backoff(max_retries=3)
    async def refine_product_name(self, original_name: str) -> str:
        prompt = f"입력된 상품명에서 브랜드명, 특수문자, 중복 단어를 제거하고 검색에 최적화된 깔끔한 상품명만 추출해줘. 수량 단위는 '개'로 표준화해(예: 10p -> 10개). 응답은 반드시 {{\"refined_name\": \"...\"}} 형식의 JSON이어야 해. 입력: {original_name}"
        return await self._generate_json(prompt, "refined_name", original_name)

    async def generate_synonyms(self, refined_name: str) -> list[str]:
        prompt = f"다음 상품명과 연관된 쇼핑 검색 키워드 동의어를 3개만 추천해줘. 예: '무선 이어폰' -> '블루투스 이어셋'. 응답은 콤마로 구분. 입력: {refined_name}"
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    self.base_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
                res.raise_for_status()
                data = res.json()
                content = data["choices"][0]["message"]["content"]
                return [s.strip() for s in content.split(",")]
        except Exception:
            return []

    async def verify_trademark(self, word: str) -> bool:
        prompt = f"다음 단어가 특정 브랜드 이름이거나 상표권 침해 소지가 있는 고유명사인가요? 응답은 반드시 {{\"is_trademark\": true/false}} 형식의 JSON이어야 합니다. 단어: {word}"
        return await self._generate_json(prompt, "is_trademark", False)

    async def _generate_json(self, prompt: str, key: str, fallback):
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    self.base_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"}
                    }
                )
                res.raise_for_status()
                data = res.json()
                content = data["choices"][0]["message"]["content"]
                result = json.loads(content)
                return result.get(key, fallback)
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return fallback
