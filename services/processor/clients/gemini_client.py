import google.generativeai as genai
import json
import logging
from config import settings
from utils.backoff import retry_with_backoff

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    @retry_with_backoff(max_retries=3)
    async def refine_product_name(self, original_name: str) -> str:
        """
        Gemini를 이용한 상품명 정제 로직 (3단계 재시도 전략 포함)
        """
        prompts = [
            # 1단계: 표준 정제
            f"입력된 상품명에서 브랜드명, 특수문자, 중복 단어를 제거하고 검색에 최적화된 깔끔한 상품명만 추출해줘. 수량 단위는 '개'로 표준화해(예: 10p -> 10개). 응답은 반드시 {{\"refined_name\": \"...\"}} 형식의 JSON이어야 해. 입력: {original_name}",
            
            # 2단계: 더 간결한 정제 (실패 시)
            f"상품명을 쇼핑 검색에 유리하게 정제해줘. 브랜드와 불필요한 미사여구는 빼고 핵심 단어만 남겨. 응답 형식: {{\"refined_name\": \"...\"}}. 입력: {original_name}",
            
            # 3단계: 최소한의 가공 (최종 시도)
            f"다음 상품명에서 특수문자만 제거하고 이름을 다듬어줘. 응답 형식: {{\"refined_name\": \"...\"}}. 입력: {original_name}"
        ]

        for i, prompt in enumerate(prompts):
            try:
                # generate_content_async는 동기 라이브러리를 래핑한 것일 수 있으므로 주의
                response = await self.model.generate_content_async(prompt)
                text = response.text
                
                # JSON 파싱 시도
                # 때때로 LLM이 ```json ... ``` 로 감싸서 주기도 함
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "{" in text and "}" in text:
                    text = text[text.find("{"):text.rfind("}")+1]
                
                result = json.loads(text)
                if "refined_name" in result:
                    return result["refined_name"]
            except Exception as e:
                logger.error(f"Gemini refinement attempt {i+1} failed: {e}")
                if i == len(prompts) - 1:
                    # 모든 시도 실패 시 원본 반환
                    return original_name
        
        return original_name
