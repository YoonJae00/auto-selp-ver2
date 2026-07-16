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

class QuotaExceededError(Exception):
    """API 사용량 초과 시 발생하는 예외 (내부 재시도 의미)"""


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


# 어댑터 스튜디오 전용 모델. 어댑터 생성은 1회성 고비용 허용 작업이라 프론티어급을 쓴다.
# (get_llm_client 사용처는 전부 어댑터 스튜디오 경로 — 대량 크롤 런타임은 LLM을 쓰지 않는다.)
# config.openai_model 로 오버라이드 가능. 비어 있으면 아래 기본값.
_OPENAI_MODEL_DEFAULT = "gpt-5.6-luna"
# GPT-5.6 계열 reasoning effort. Chat Completions는 reasoning_effort 파라미터.
# SDK 1.51.2에는 정식 kwarg가 없어 extra_body로 그대로 API에 전달한다(구 SDK 안전).
_REASONING_EXTRA_BODY = {"reasoning_effort": "medium"}


def _openai_model() -> str:
    from app.config import load_config
    return (load_config().openai_model or "").strip() or _OPENAI_MODEL_DEFAULT


def _openai_vision(model: str) -> bool:
    # GPT-5.6 3형제(sol/terra/luna) 포함 현대 모델은 전부 비전 지원.
    return model.startswith(("gpt-4o", "gpt-4.1", "gpt-5", "o1", "o3", "o4"))


class OpenAIClient(LLMClient):
    async def generate(
        self, system_prompt: str, user_prompt: str, image_paths: list[str] | None = None
    ) -> str:
        from openai import AsyncOpenAI

        model_name = _openai_model()
        images = _read_images(image_paths) if _openai_vision(model_name) else []
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
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    extra_body=_REASONING_EXTRA_BODY,
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


def get_llm_client(provider: str = "openai") -> LLMClient:
    # 이 앱의 LLM은 OpenAI 단일 제공사다. provider 인자는 하위호환으로 받되 무시한다.
    return OpenAIClient("openai")
