from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analyzer.llm_client import OpenAIClient


@pytest.mark.asyncio
async def test_openai_client_sets_medium_reasoning_effort() -> None:
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
    assert api.chat.completions.create.await_args.kwargs["reasoning_effort"] == "medium"
