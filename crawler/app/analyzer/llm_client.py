from __future__ import annotations

import base64
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from app.credentials.store import load_llm_api_key

logger = logging.getLogger(__name__)

# 이미지 첨부는 보강일 뿐 — 읽기 실패/과대 파일은 조용히 건너뛰고 텍스트만 진행한다.
_MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _read_images(image_paths: list[str] | None) -> list[bytes]:
    """존재하고 크기 제한 이하인 이미지 파일만 bytes로 읽는다. 절대 예외를 던지지 않는다."""
    out: list[bytes] = []
    for path in image_paths or []:
        try:
            if not path or not os.path.isfile(path):
                continue
            if os.path.getsize(path) > _MAX_IMAGE_BYTES:
                logger.warning("이미지 첨부 생략 (크기 초과): %s", path)
                continue
            with open(path, "rb") as fh:
                out.append(fh.read())
        except Exception:
            continue
    return out


def _log_llm_call(provider: str, system_prompt: str, user_prompt: str, image_count: int = 0) -> None:
    logger.info(
        "LLM request provider=%s images=%d\n--- system ---\n%s\n--- user ---\n%s",
        provider, image_count, system_prompt, user_prompt,
    )


def _log_llm_response(provider: str, response: str) -> None:
    logger.info("LLM response provider=%s\n%s", provider, response)

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
    async def generate(
        self, system_prompt: str, user_prompt: str, image_paths: list[str] | None = None
    ) -> str:
        raise NotImplementedError


# 하드코딩 모델 상수. gemini 2.x flash / gpt-5.x mini 모두 비전 지원.
# 모델을 텍스트 전용으로 바꾸면 아래 플래그를 False로 내려 이미지가 조용히 무시되게 한다.
_GEMINI_MODEL = "gemini-2.0-flash-lite"
_GEMINI_VISION = "flash" in _GEMINI_MODEL or "-pro-vision" in _GEMINI_MODEL or "gemini-1.5" in _GEMINI_MODEL
_OPENAI_MODEL = "gpt-5.4-mini"
_OPENAI_VISION = _OPENAI_MODEL.startswith(("gpt-4o", "gpt-4.1", "gpt-5", "o1", "o3", "o4"))


class GeminiClient(LLMClient):
    async def generate(
        self, system_prompt: str, user_prompt: str, image_paths: list[str] | None = None
    ) -> str:
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(_GEMINI_MODEL)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        images = _read_images(image_paths) if _GEMINI_VISION else []
        # 0.8.6: content part로 {"mime_type", "data": bytes} blob dict을 받는다(inline_data).
        contents: Any = (
            [full_prompt, *({"mime_type": "image/png", "data": b} for b in images)]
            if images else full_prompt
        )
        _log_llm_call(self.provider, system_prompt, user_prompt, len(images))
        try:
            response = await model.generate_content_async(contents)
            _log_llm_response(self.provider, response.text)
            return response.text
        except _GeminiQuotaError:
            raise QuotaExceededError(
                "Gemini API 사용량이 초과되었습니다. 무료 할당량이 소진되었을 수 있습니다."
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini 호출 중 오류: {exc}") from exc


class OpenAIClient(LLMClient):
    async def generate(
        self, system_prompt: str, user_prompt: str, image_paths: list[str] | None = None
    ) -> str:
        from openai import AsyncOpenAI

        images = _read_images(image_paths) if _OPENAI_VISION else []
        if images:
            user_content: Any = [{"type": "text", "text": user_prompt}]
            for b in images:
                uri = "data:image/png;base64," + base64.b64encode(b).decode("ascii")
                user_content.append({"type": "image_url", "image_url": {"url": uri}})
        else:
            user_content = user_prompt
        _log_llm_call(self.provider, system_prompt, user_prompt, len(images))
        try:
            async with AsyncOpenAI(api_key=self.api_key, max_retries=3, timeout=60.0) as client:
                response = await client.chat.completions.create(
                    model=_OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                )
            content = response.choices[0].message.content or ""
            _log_llm_response(self.provider, content)
            return content
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
