from __future__ import annotations

from typing import Any


class ServerClient:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        self.base_url = base_url
        self.token = token

    def push_products(self, supplier_id: str) -> dict[str, Any]:
        raise NotImplementedError("Server sync is planned for phase 2. Use Excel export for now.")

    def check_connection(self) -> bool:
        raise NotImplementedError("Server sync is planned for phase 2.")
