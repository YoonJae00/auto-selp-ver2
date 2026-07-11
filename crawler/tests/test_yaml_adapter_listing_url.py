from __future__ import annotations

from types import SimpleNamespace

from app.crawlers.yaml_adapter import YAMLAdapter


def _adapter(url_template: str = "", start: int = 1, page_param: str = "page") -> YAMLAdapter:
    adapter = YAMLAdapter.__new__(YAMLAdapter)
    adapter.adapter = SimpleNamespace(
        adapter=SimpleNamespace(
            categories=SimpleNamespace(url_template=url_template),
            listing=SimpleNamespace(
                pagination=SimpleNamespace(start=start, page_param=page_param)
            ),
        )
    )
    return adapter


def test_listing_url_uses_template_when_present() -> None:
    adapter = _adapter(url_template="http://x/list?cate={category_id}&page={page}")
    assert adapter._listing_url("24", "http://x/cat/24", 1) == "http://x/list?cate=24&page=1"


def test_listing_url_uses_real_category_url_when_template_empty() -> None:
    # 버그였던 지점: url_template이 비면 예전엔 category_id("list.html")를 URL로 써서
    # goto가 실패했다. 이제 discovery가 찾은 실제 카테고리 URL을 쓴다.
    adapter = _adapter(url_template="")
    url = "http://localhost:9000/kitchen/list.html"
    assert adapter._listing_url("list.html", url, 1) == url
    assert adapter._listing_url("list.html", url, 2) == url + "?page=2"


def test_listing_url_appends_page_param_to_existing_query() -> None:
    adapter = _adapter(url_template="")
    assert adapter._listing_url("x", "http://x/list?cate=3", 2) == "http://x/list?cate=3&page=2"


def test_listing_url_falls_back_to_category_id_when_no_url() -> None:
    adapter = _adapter(url_template="")
    assert adapter._listing_url("http://x/full", None, 1) == "http://x/full"


def test_categories_config_accepts_and_defaults_entries() -> None:
    from app.analyzer.adapter_schema import CategoriesConfig

    cfg = CategoriesConfig.model_validate(
        {"mode": "tree", "entries": [{"name": "주방", "url": "http://x/k"}]}
    )
    assert cfg.entries[0].name == "주방"
    assert cfg.entries[0].url == "http://x/k"
    assert CategoriesConfig().entries == []  # 기본값은 빈 목록


def test_discover_categories_uses_saved_entries() -> None:
    import asyncio

    adapter = YAMLAdapter.__new__(YAMLAdapter)
    adapter.adapter = SimpleNamespace(
        adapter=SimpleNamespace(
            categories=SimpleNamespace(
                entries=[
                    SimpleNamespace(name="주방", url="http://localhost:9000/kitchen/list.html"),
                    SimpleNamespace(name="욕실", url="http://localhost:9000/bath/list.html?cate=3"),
                ]
            )
        )
    )
    result = asyncio.run(adapter.discover_categories())
    assert [e.name for e in result] == ["주방", "욕실"]
    assert result[0].url == "http://localhost:9000/kitchen/list.html"
    assert result[0].category_id == "list.html"
    assert result[1].category_id == "3"  # ?cate=3 → 3


def test_crawl_category_stops_when_pages_repeat_same_links() -> None:
    """사이트가 page 파라미터를 무시하고 같은 목록을 반복해도, 중복 링크 감지로
    max_pages를 다 돌지 않고 고유 상품만 1회 수집하고 종료해야 한다 (450 버그 방지)."""
    import asyncio
    from app.crawlers.base import CrawlResult
    from app.schema.standard import StandardProduct

    class _El:
        def __init__(self, href): self._href = href
        async def get_attribute(self, _n): return self._href

    class _Page:
        async def goto(self, *a, **k): ...
        async def query_selector(self, _s): return None       # stop_indicator 없음
        async def query_selector_all(self, _s):
            return [_El("/d?p=1"), _El("/d?p=2")]               # 매 페이지 같은 2개
        async def close(self): ...

    class _Engine:
        async def new_page(self): return _Page()

    adapter = YAMLAdapter.__new__(YAMLAdapter)
    adapter.engine = _Engine()
    adapter.delay_seconds = 0
    adapter.supplier_name = "t"
    adapter.adapter = SimpleNamespace(adapter=SimpleNamespace(
        login=SimpleNamespace(required=False, login_url=None),
        base_url="http://x/",
        browser=SimpleNamespace(wait_until="load"),
        categories=SimpleNamespace(url_template=""),
        listing=SimpleNamespace(
            pagination=SimpleNamespace(start=1, page_param="page", stop_indicator=""),
            product_link=SimpleNamespace(selector=".p", attribute="href"),
        ),
    ))

    async def _fake_product(url, category_path):
        return CrawlResult(
            StandardProduct("t", None, url, "available", "n", None, None, None, None), []
        )
    adapter._crawl_product = _fake_product

    async def run():
        return [r async for r in adapter.crawl_category("cat", 50, "http://x/list")]

    results = asyncio.run(run())
    assert len(results) == 2  # 고유 2개만, 50페이지 반복 아님


def test_validate_export_scope_none_means_all(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.models import Base, Product, Supplier
    from app.exporters.validation import validate_export_scope

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Supplier(id="s1", name="shop", base_url="http://x"))
    s.add(Product(id="p1", supplier_id="s1", supplier_name="shop",
                  supplier_product_code="C1", supplier_status="available",
                  raw_product_name="상품", supply_price=1000, main_image_url="http://x/i.jpg", origin="국산"))
    s.commit()
    v = validate_export_scope(s, None)  # 전체
    assert v.product_count == 1
    assert v.blocking_count == 0        # 예전엔 None==비교로 0개→blocking=1 오판
    s.close()
