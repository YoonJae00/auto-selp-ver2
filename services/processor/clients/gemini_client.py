import google.generativeai as genai
import httpx
import json
import logging
from config import settings
from utils.backoff import retry_with_backoff
from clients.llm_client import LLMClient, smartstore_name_prompt
from utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

class GeminiClient(LLMClient):
    def __init__(self, prompt_manager: PromptManager = None, model: str = 'gemini-3.1-flash-lite'):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(model)
        self.prompt_manager = prompt_manager

    async def generate_smartstore_name_candidates(
        self,
        refined_name: str,
        keywords: list[str],
        brand_name: str | None = None,
        category_path: str | None = None,
    ) -> list[str]:
        prompt = smartstore_name_prompt(refined_name, keywords, brand_name, category_path)
        try:
            response = await self.model.generate_content_async(prompt)
            text = response.text
            if "```json" in text:
                text = text.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "{" in text and "}" in text:
                text = text[text.find("{"):text.rfind("}") + 1]
            candidates = json.loads(text).get("candidates")
            if not isinstance(candidates, list) or len(candidates) != 3 or not all(isinstance(item, str) for item in candidates):
                return []
            candidates = [item.strip() for item in candidates]
            return candidates if all(candidates) else []
        except Exception as error:
            logger.error("Gemini Smartstore candidate generation failed: %s", error)
            return []

    @retry_with_backoff(max_retries=3)
    async def refine_product_name(self, original_name: str) -> str:
        # Default prompts
        default_prompts = [
            f"입력된 상품명에서 브랜드명, 특수문자, 중복 단어를 제거하고 검색에 최적화된 깔끔한 상품명만 추출해줘. 수량 단위는 '개'로 표준화해. 응답은 반드시 {{\"refined_name\": \"...\"}} 형식의 JSON이어야 해. 입력: {original_name}",
            f"상품명을 쇼핑 검색에 유리하게 정제해줘. 브랜드와 불필요한 미사여구는 빼고 핵심 단어만 남겨. 응답 형식: {{\"refined_name\": \"...\"}}. 입력: {original_name}",
            f"다음 상품명에서 특수문자만 제거하고 이름을 다듬어줘. 응답 형식: {{\"refined_name\": \"...\"}}. 입력: {original_name}"
        ]
        
        prompts = []
        if self.prompt_manager:
            for i in range(1, 4):
                p = await self.prompt_manager.get_prompt(f"refine_stage_{i}", default_prompts[i-1])
                # Inject variable
                prompts.append(p.replace("{original_name}", original_name))
        else:
            prompts = default_prompts

        for i, prompt in enumerate(prompts):
            try:
                response = await self.model.generate_content_async(prompt)
                text = response.text
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
                    return original_name
        return original_name

    async def get_synonyms(self, refined_name: str) -> list[str]:
        try:
            default_prompt = f"다음 상품명과 연관된 쇼핑 검색 키워드 동의어를 3개만 추천해줘. 예: '무선 이어폰' -> '블루투스 이어셋'. 응답은 콤마로 구분. 입력: {refined_name}"
            prompt = default_prompt
            if self.prompt_manager:
                p = await self.prompt_manager.get_prompt("get_synonyms", default_prompt)
                prompt = p.replace("{refined_name}", refined_name)
                
            response = await self.model.generate_content_async(prompt)
            return [s.strip() for s in response.text.split(",")]
        except Exception as e:
            logger.error(f"Gemini synonym expansion failed: {e}")
            return []

    async def classify_brand_keywords(self, keywords: list[str]) -> dict:
        """
        키워드 목록을 배치로 분류: 브랜드 의심 vs 일반 명사
        LLM 1회 호출로 처리
        """
        if not keywords:
            return {"brand_suspected": [], "generic": []}
        
        kw_list_str = "\n".join(f"- {kw}" for kw in keywords)
        prompt = (
            f"다음 키워드 목록을 분류해줘.\n"
            f"기준: 특정 회사/제품의 고유 브랜드명이나 상표명이 포함된 경우 brand_suspected, "
            f"일반적인 제품 카테고리나 소재/기능을 설명하는 일반 명사인 경우 generic.\n"
            f"예시) '가스 쇼바' → generic, '3BOSS' → brand_suspected, '다이슨' → brand_suspected, '무보링 댐퍼' → generic\n"
            f"\n키워드 목록:\n{kw_list_str}\n"
            f"\n반드시 아래 JSON 형식으로만 응답해. 설명 없이 JSON만:\n"
            f'{{"brand_suspected": ["..."], "generic": ["..."]}}'
        )
        
        try:
            response = await self.model.generate_content_async(prompt)
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "{" in text and "}" in text:
                text = text[text.find("{"):text.rfind("}")+1]
            
            result = json.loads(text)
            brand_suspected = result.get("brand_suspected", [])
            generic = result.get("generic", [])
            
            # LLM이 누락한 키워드는 안전하게 generic으로 처리
            classified = set(brand_suspected) | set(generic)
            unclassified = [kw for kw in keywords if kw not in classified]
            generic.extend(unclassified)
            
            logger.info(f"브랜드 분류: brand_suspected={brand_suspected}, generic_count={len(generic)}")
            return {"brand_suspected": brand_suspected, "generic": generic}
        except Exception as e:
            logger.error(f"Gemini brand classification failed: {e}")
            # 실패 시 모두 generic으로 처리
            return {"brand_suspected": [], "generic": keywords}

    async def _download_image(self, url: str) -> bytes | None:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
                if response.status_code == 200:
                    return response.content
        except Exception as e:
            logger.error(f"Failed to download image {url}: {e}")
        return None

    async def extract_product_attributes(self, refined_name: str, image_urls: list[str], attributes: list) -> dict:
        if not image_urls:
            return {}
        # Download first 3 details page images
        image_parts = []
        for url in image_urls[:3]:
            img_bytes = await self._download_image(url)
            if img_bytes:
                image_parts.append({
                    "mime_type": "image/jpeg",
                    "data": img_bytes
                })
        
        attr_schema_str = json.dumps(attributes, ensure_ascii=False)
        prompt = (
            f"상품명: {refined_name}\n"
            f"대상 속성 요구사항:\n{attr_schema_str}\n\n"
            f"상세 이미지들을 분석하여 요구사항에 맞는 속성(값)들을 추출해줘.\n"
            f"반드시 다음 JSON 포맷의 구조로 설명 없이 JSON만 응답해:\n"
            f'{{"속성명": "추출값", ...}}'
        )
        
        try:
            contents = [prompt] + image_parts
            response = await self.model.generate_content_async(contents)
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "{" in text and "}" in text:
                text = text[text.find("{"):text.rfind("}")+1]
            return json.loads(text)
        except Exception as e:
            logger.error(f"Gemini attribute extraction failed: {e}")
            return {}
