import openai
import json
import logging
from config import settings
from utils.backoff import retry_with_backoff
from clients.llm_client import LLMClient

logger = logging.getLogger(__name__)

class OpenAIClient(LLMClient):
    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-5.4-nano"

    @retry_with_backoff(max_retries=3)
    async def refine_product_name(self, original_name: str) -> str:
        prompts = [
            f"입력된 상품명에서 브랜드명, 특수문자, 중복 단어를 제거하고 검색에 최적화된 깔끔한 상품명만 추출해줘. 수량 단위는 '개'로 표준화해. 응답은 반드시 {{\"refined_name\": \"...\"}} 형식의 JSON이어야 해. 입력: {original_name}",
            f"상품명을 쇼핑 검색에 유리하게 정제해줘. 브랜드와 불필요한 미사여구는 빼고 핵심 단어만 남겨. 응답 형식: {{\"refined_name\": \"...\"}}. 입력: {original_name}",
            f"다음 상품명에서 특수문자만 제거하고 이름을 다듬어줘. 응답 형식: {{\"refined_name\": \"...\"}}. 입력: {original_name}"
        ]

        for i, prompt in enumerate(prompts):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                text = response.choices[0].message.content
                result = json.loads(text)
                if "refined_name" in result:
                    return result["refined_name"]
            except Exception as e:
                logger.error(f"OpenAI refinement attempt {i+1} failed: {e}")
                if i == len(prompts) - 1:
                    return original_name
        return original_name

    async def get_synonyms(self, refined_name: str) -> list[str]:
        try:
            prompt = f"다음 상품명과 연관된 쇼핑 검색 키워드 동의어를 3개만 추천해줘. 예: '무선 이어폰' -> '블루투스 이어셋'. 응답은 콤마로 구분. 입력: {refined_name}"
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            return [s.strip() for s in response.choices[0].message.content.split(",")]
        except Exception as e:
            logger.error(f"OpenAI synonym expansion failed: {e}")
            return []
