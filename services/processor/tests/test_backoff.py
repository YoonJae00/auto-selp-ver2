import pytest
import httpx
import asyncio
from unittest.mock import MagicMock, patch
from services.processor.utils.backoff import retry_with_backoff

@pytest.mark.asyncio
async def test_retry_with_backoff_success_after_retry():
    mock_func = MagicMock()
    # First call returns 429, second call returns success
    mock_func.side_effect = [
        httpx.HTTPStatusError("429 Too Many Requests", request=MagicMock(), response=httpx.Response(429)),
        "success"
    ]
    
    decorated_func = retry_with_backoff(max_retries=2, base_delay=0.01)(mock_func)
    
    with patch("asyncio.sleep", return_value=None) as mock_sleep:
        result = await decorated_func()
    
    assert result == "success"
    assert mock_func.call_count == 2
    mock_sleep.assert_called_once_with(0.01)
