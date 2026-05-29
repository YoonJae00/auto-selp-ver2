import base64
import logging
import time

import bcrypt
import httpx

from config import settings

logger = logging.getLogger(__name__)

# Module-level token cache shared across all instances
_token_cache: dict = {"access_token": None, "expires_at": 0.0}


class NaverCommerceClient:
    """
    Naver Commerce API client with bcrypt-based OAuth2 client credentials flow.

    Token acquisition uses a bcrypt-signed timestamp to produce the
    ``client_secret_sign`` parameter.  Tokens are cached at the module level
    and reused for up to 3 500 seconds (one hour minus a safety margin).
    """

    BASE_URL = "https://api.commerce.naver.com/external"

    def __init__(self) -> None:
        self.client_id: str = settings.NAVER_COMMERCE_CLIENT_ID
        self.client_secret: str = settings.NAVER_COMMERCE_CLIENT_SECRET

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _get_access_token(self) -> str:
        """Return a valid Bearer token, fetching a new one when the cache
        is empty or expired."""
        global _token_cache

        if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
            return _token_cache["access_token"]

        token = await self._fetch_new_token()
        if token:
            _token_cache["access_token"] = token
            _token_cache["expires_at"] = time.time() + 3500  # 1 h − safety margin
        return token or ""

    async def _fetch_new_token(self) -> str | None:
        """Request a fresh OAuth2 token from the Naver Commerce API.

        The signature is:
            base64( bcrypt( f"{client_id}_{timestamp_ms}", client_secret_as_salt ) )

        The ``client_secret`` value already carries the bcrypt prefix
        (``$2a$04$...``) so it is used directly as the salt.
        """
        timestamp_ms = int(time.time() * 1000)
        password = f"{self.client_id}_{timestamp_ms}".encode("utf-8")
        salt = self.client_secret.encode("utf-8")

        try:
            hashed = bcrypt.hashpw(password, salt)
            client_secret_sign = base64.b64encode(hashed).decode("utf-8")
        except Exception as exc:
            logger.error("NaverCommerceClient: failed to build bcrypt signature: %s", exc)
            return None

        payload = {
            "client_id": self.client_id,
            "timestamp": str(timestamp_ms),
            "client_secret_sign": client_secret_sign,
            "grant_type": "client_credentials",
            "type": "SELF",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/v1/oauth2/token",
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                data = response.json()
                return data.get("access_token")
        except Exception as exc:
            logger.error("NaverCommerceClient: token fetch failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # API methods
    # ------------------------------------------------------------------

    async def get_category_attributes(self, category_id: str) -> list[dict]:
        """Fetch attribute definitions for a Naver Commerce category.

        Returns a list of dicts with keys:
            - ``attributeSeq``
            - ``attributeName``
            - ``attributeClassificationType``  (SINGLE_SELECT / MULTI_SELECT / RANGE)
            - ``required``  (bool)

        Returns an empty list on any error.
        """
        token = await self._get_access_token()
        if not token:
            logger.error("NaverCommerceClient: skipping get_category_attributes — no token")
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/v1/product-attributes/attributes",
                    params={"categoryId": category_id},
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                data = response.json()
                # The API returns the list directly or wrapped in a key.
                if isinstance(data, list):
                    return data
                return data if isinstance(data, list) else []
        except Exception as exc:
            logger.error(
                "NaverCommerceClient: get_category_attributes failed (category=%s): %s",
                category_id,
                exc,
            )
            return []

    async def get_category_attribute_values(self, category_id: str) -> list[dict]:
        """Fetch allowed attribute values for a Naver Commerce category.

        Returns a list of dicts with keys:
            - ``attributeSeq``
            - ``attributeValueSeq``
            - ``exposureOrder``

        Returns an empty list on any error.
        """
        token = await self._get_access_token()
        if not token:
            logger.error(
                "NaverCommerceClient: skipping get_category_attribute_values — no token"
            )
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/v1/product-attributes/attribute-values",
                    params={"categoryId": category_id},
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                data = response.json()
                if isinstance(data, list):
                    return data
                return data if isinstance(data, list) else []
        except Exception as exc:
            logger.error(
                "NaverCommerceClient: get_category_attribute_values failed (category=%s): %s",
                category_id,
                exc,
            )
            return []
