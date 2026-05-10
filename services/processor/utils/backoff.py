import asyncio
import functools
import httpx
import logging

logger = logging.getLogger(__name__)

def retry_with_backoff(max_retries: int = 5, base_delay: float = 1.0):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            retries = 0
            while True:
                try:
                    return await func(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and retries < max_retries:
                        delay = base_delay * (2 ** retries)
                        
                        # Honor Retry-After header if present
                        retry_after = e.response.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            delay = float(retry_after)
                        
                        logger.warning(f"Rate limited (429). Retrying in {delay}s... (Attempt {retries + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        retries += 1
                        continue
                    raise e
        return wrapper
    return decorator
