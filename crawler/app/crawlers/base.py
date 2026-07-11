from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.schema.standard import StandardOption, StandardProduct


@dataclass
class CategoryEntry:
    category_id: str
    name: str
    path: str
    url: str
    product_count: int | None = None
    children: list["CategoryEntry"] = field(default_factory=list)


@dataclass
class CrawlResult:
    product: StandardProduct
    options: list[StandardOption]


@dataclass
class StockSnapshotData:
    supplier_product_code: str
    supplier_status: str | None
    supply_price: int | None
    option_stock: dict[str, int | None] = field(default_factory=dict)


class BaseAdapter:
    async def discover_categories(self) -> list[CategoryEntry]:
        raise NotImplementedError

    async def crawl_category(
        self,
        category_id: str,
        max_pages: int,
        category_url: str | None = None,
    ) -> AsyncIterator[CrawlResult]:
        raise NotImplementedError
        if False:
            yield CrawlResult(StandardProduct("", None, "", "", "", None, None, None, None), [])

    async def stock_check(
        self,
        category_id: str | None = None,
        category_url: str | None = None,
    ) -> AsyncIterator[StockSnapshotData]:
        raise NotImplementedError
        if False:
            yield StockSnapshotData("", None, None)

    async def close(self) -> None:
        raise NotImplementedError
