from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analyzer.llm_client import (
    OpenAIClient,
    _openai_model,
    _openai_vision,
    _read_images,
    get_llm_client,
)
from app.config import AppConfig


def _png(path, size: int = 100) -> str:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * (size - 8))
    return str(path)


# ----- _read_images (best-effort, 절대 예외 안 던짐) -----

def test_read_images_skips_missing_and_oversized(tmp_path) -> None:
    good = _png(tmp_path / "a.png")
    big = _png(tmp_path / "big.png", size=9 * 1024 * 1024)
    imgs = _read_images([good, big, str(tmp_path / "nope.png"), ""])
    assert len(imgs) == 1  # 존재+크기OK인 것만
    assert imgs[0].startswith(b"\x89PNG")


def test_read_images_none_is_empty() -> None:
    assert _read_images(None) == []


# ----- OpenAI 비전 첨부 -----

@pytest.mark.asyncio
async def test_openai_attaches_image_url_part(tmp_path) -> None:
    img = _png(tmp_path / "shot.png")
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "ok"
    api = MagicMock()
    api.chat.completions.create = AsyncMock(return_value=response)

    with (
        patch("app.analyzer.llm_client.load_llm_api_key", return_value="k"),
        patch("openai.AsyncOpenAI") as async_openai,
    ):
        async_openai.return_value.__aenter__ = AsyncMock(return_value=api)
        async_openai.return_value.__aexit__ = AsyncMock(return_value=None)
        result = await OpenAIClient("openai").generate("sys", "usr", image_paths=[img])

    assert result == "ok"
    user_msg = api.chat.completions.create.await_args.kwargs["messages"][1]
    parts = user_msg["content"]
    assert isinstance(parts, list)
    assert parts[0] == {"type": "text", "text": "usr"}
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_openai_missing_image_falls_back_to_text(tmp_path) -> None:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "ok"
    api = MagicMock()
    api.chat.completions.create = AsyncMock(return_value=response)

    with (
        patch("app.analyzer.llm_client.load_llm_api_key", return_value="k"),
        patch("openai.AsyncOpenAI") as async_openai,
    ):
        async_openai.return_value.__aenter__ = AsyncMock(return_value=api)
        async_openai.return_value.__aexit__ = AsyncMock(return_value=None)
        await OpenAIClient("openai").generate("sys", "usr", image_paths=[str(tmp_path / "gone.png")])

    # 파일 없음 → 텍스트 폴백(문자열 content)
    assert api.chat.completions.create.await_args.kwargs["messages"][1]["content"] == "usr"


# ----- 모델 선택: luna 기본값 + config 오버라이드 -----

def test_default_model_is_luna_and_vision_capable() -> None:
    with patch("app.config.load_config", return_value=AppConfig()):
        assert _openai_model() == "gpt-5.6-luna"
    assert _openai_vision("gpt-5.6-luna") is True  # 5.6 계열은 비전 지원


def test_config_overrides_model_name() -> None:
    cfg = AppConfig(openai_model="gpt-4.1")
    with patch("app.config.load_config", return_value=cfg):
        assert _openai_model() == "gpt-4.1"


def test_get_llm_client_always_returns_openai() -> None:
    # provider 인자는 하위호환으로 받되 무시하고 항상 OpenAI 반환.
    with patch("app.analyzer.llm_client.load_llm_api_key", return_value="k"):
        assert isinstance(get_llm_client("gemini"), OpenAIClient)
        assert isinstance(get_llm_client(), OpenAIClient)


@pytest.mark.asyncio
async def test_openai_passes_reasoning_effort_medium_via_extra_body() -> None:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "ok"

    api = MagicMock()
    api.chat.completions.create = AsyncMock(return_value=response)

    with (
        patch("app.analyzer.llm_client.load_llm_api_key", return_value="test-key"),
        patch("openai.AsyncOpenAI") as async_openai,
    ):
        async_openai.return_value.__aenter__ = AsyncMock(return_value=api)
        async_openai.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await OpenAIClient("openai").generate("system", "user")

    assert result == "ok"
    # 구 SDK(1.51.2)에는 reasoning_effort kwarg가 없어 extra_body로 전달한다.
    kwargs = api.chat.completions.create.await_args.kwargs
    assert kwargs["extra_body"] == {"reasoning_effort": "medium"}
    assert "reasoning_effort" not in kwargs  # 정식 kwarg가 아니라 extra_body 경유
