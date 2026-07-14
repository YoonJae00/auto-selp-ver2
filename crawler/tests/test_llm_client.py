from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analyzer.llm_client import GeminiClient, OpenAIClient, _read_images


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


# ----- Gemini 비전 첨부 -----

@pytest.mark.asyncio
async def test_gemini_attaches_image_as_inline_blob(tmp_path) -> None:
    img = _png(tmp_path / "shot.png")
    captured = {}

    async def fake_generate(contents):
        captured["contents"] = contents
        return MagicMock(text="ok")

    model = MagicMock()
    model.generate_content_async = fake_generate
    fake_genai = MagicMock()
    fake_genai.GenerativeModel.return_value = model

    with (
        patch("app.analyzer.llm_client.load_llm_api_key", return_value="k"),
        patch.dict("sys.modules", {"google.generativeai": fake_genai}),
    ):
        result = await GeminiClient("gemini").generate("sys", "usr", image_paths=[img])

    assert result == "ok"
    contents = captured["contents"]
    assert isinstance(contents, list)  # 이미지 있으면 [prompt, blob...]
    blob = contents[1]
    assert blob["mime_type"] == "image/png"
    assert blob["data"].startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_gemini_without_images_passes_plain_prompt() -> None:
    captured = {}

    async def fake_generate(contents):
        captured["contents"] = contents
        return MagicMock(text="ok")

    model = MagicMock()
    model.generate_content_async = fake_generate
    fake_genai = MagicMock()
    fake_genai.GenerativeModel.return_value = model

    with (
        patch("app.analyzer.llm_client.load_llm_api_key", return_value="k"),
        patch.dict("sys.modules", {"google.generativeai": fake_genai}),
    ):
        await GeminiClient("gemini").generate("sys", "usr")

    assert isinstance(captured["contents"], str)  # image_paths=None → 기존 경로 무변형


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


@pytest.mark.asyncio
async def test_openai_client_omits_reasoning_effort_for_sdk_compatibility() -> None:
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
    assert "reasoning_effort" not in api.chat.completions.create.await_args.kwargs
