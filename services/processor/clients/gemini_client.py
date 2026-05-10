import google.generativeai as genai
import json
import logging
from config import settings
from utils.backoff import retry_with_backoff
from clients.llm_base import LLMClient

logger = logging.getLogger(__name__)

class GeminiClient(LLMClient):
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        # 최신 모델 gemini-2.0-flash 사용
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    @retry_with_backoff(max_retries=3)
    async def refine_product_name(self, original_name: str) -> str:
        prompts = [
            f"입력된 상품명에서 브랜드명, 특수문자, 중복 단어를 제거하고 검색에 최적화된 깔끔한 상품명만 추출해줘. 수량 단위는 '개'로 표준화해(예: 10p -> 10개). 응답은 반드시 {{\"refined_name\": \"...\"}} 형식의 JSON이어야 해. 입력: {original_name}",
            f"상품명을 쇼핑 검색에 유리하게 정제해줘. 브랜드와 불필요한 미사여구는 빼고 핵심 단어만 남겨. 응답 형식: {{\"refined_name\": \"...\"}}. 입력: {original_name}",
            f"다음 상품명에서 특수문자만 제거하고 이름을 다듬어줘. 응답 형식: {{\"refined_name\": \"...\"}}. 입력: {original_name}"
        ]
        return await self._generate_json(prompts, "refined_name", original_name)

    async def generate_synonyms(self, refined_name: str) -> list[str]:
        prompt = f"다음 상품명과 연관된 쇼핑 검색 키워드 동의어를 3개만 추천해줘. 예: '무선 이어폰' -> '블루투스 이어셋'. 응답은 콤마로 구분. 입력: {refined_name}"
        try:
            response = await self.model.generate_content_async(prompt)
            return [s.strip() for s in response.text.split(",")]
        except Exception:
            return []

    async def verify_trademark(self, word: str) -> bool:
        # LLM에게 상표권 여부를 물어보는 로직 (의심 단어 판별)
        prompt = f"다음 단어가 특정 브랜드 이름이거나 상표권 침해 소지가 있는 고유명사인가요? 응답은 반드시 {{\"is_trademark\": true/false}} 형식의 JSON이어야 합니다. 단어: {word}"
        try:
            res = await self._generate_json([prompt], "is_trademark", False)
            return bool(res)
        except Exception:
            return False

    async def _generate_json(self, prompts: list[str], key: str, fallback):
        for i, prompt in enumerate(prompts):
            try:
                response = await self.model.generate_content_async(prompt)
                text = response.text
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "{" in text and "}" in text:
                    text = text[text.find("{"):text.rfind("}")+1]
                
                result = json.loads(text)
                if key in result:
                    return result[key]
            except Exception as e:
                logger.error(f"Gemini error (attempt {i+1}): {e}")
        return fallback
