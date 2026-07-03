from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.credentials.store import load_llm_api_key

# Import error classes with fallbacks to avoid hard dependency on optional packages
try:
    from openai import RateLimitError as _OpenAIRateLimitError
    from openai import APIConnectionError as _OpenAIConnectionError
    from openai import APIStatusError as _OpenAIStatusError
except ImportError:
    _OpenAIRateLimitError = Exception
    _OpenAIConnectionError = Exception
    _OpenAIStatusError = Exception

try:
    from google.api_core.exceptions import ResourceExhausted as _GeminiQuotaError
except ImportError:
    _GeminiQuotaError = Exception


class QuotaExceededError(Exception):
    """API 사용량 초과 시 발생하는 예외"""


class LLMClient(ABC):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.api_key = load_llm_api_key(provider)
        if self.api_key is None:
            raise ValueError(
                f"{provider} API 키가 설정되지 않았습니다. 설정 탭에서 API 키를 입력하세요."
            )

    @abstractmethod
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class GeminiClient(LLMClient):
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-lite")
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        try:
            response = await model.generate_content_async(full_prompt)
            return response.text
        except _GeminiQuotaError:
            raise QuotaExceededError(
                "Gemini API 사용량이 초과되었습니다. 무료 할당량이 소진되었을 수 있습니다."
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini 호출 중 오류: {exc}") from exc


class OpenAIClient(LLMClient):
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        from openai import AsyncOpenAI

        try:
            async with AsyncOpenAI(api_key=self.api_key, max_retries=3, timeout=60.0) as client:
                response = await client.chat.completions.create(
                    model="gpt-5.4-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
            return response.choices[0].message.content or ""
        except _OpenAIRateLimitError:
            raise QuotaExceededError(
                "OpenAI API 사용량이 초과되었습니다. 설정 탭에서 확인하세요."
            )
        except _OpenAIConnectionError:
            raise RuntimeError("OpenAI 서버에 연결할 수 없습니다.")
        except _OpenAIStatusError as e:
            raise RuntimeError(
                f"OpenAI API 오류 (HTTP {e.status_code}): {e.message}"
            )
        except Exception as exc:
            raise RuntimeError(f"OpenAI 호출 중 오류: {exc}") from exc


def get_llm_client(provider: str) -> LLMClient:
    if provider.lower() == "openai":
        return OpenAIClient(provider)
    return GeminiClient(provider)
