from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from app.crawlers.engine import PlaywrightEngine
from app.crawlers.registry import adapter_exists, load_adapter
from app.crawlers.yaml_adapter import YAMLAdapter
from app.db.models import CrawlRun, Product, ProductOption
from app.db.session import get_session


@dataclass(frozen=True)
class CrawlRequest:
    supplier_id: str
    supplier_name: str
    adapter_file: str
    categories: list[tuple[str, str]]
    max_pages: int
    delay_seconds: int
    credential_key: str | None = None


@dataclass(frozen=True)
class CategoryDiscoveryRequest:
    supplier_name: str
    adapter_file: str
    credential_key: str | None = None


class _AsyncThread(QThread):
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[Any] | None = None

    def requestInterruption(self) -> None:  # noqa: N802
        super().requestInterruption()
        loop, task = self._loop, self._task
        if loop is not None and task is not None and loop.is_running():
            loop.call_soon_threadsafe(task.cancel)

    cancel = requestInterruption

    def _execute(self, coroutine) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        task = loop.create_task(coroutine)
        self._task = task
        if self.isInterruptionRequested():
            task.cancel()
        try:
            loop.run_until_complete(task)
        finally:
            self._task = None
            self._loop = None
            asyncio.set_event_loop(None)
            loop.close()


class CategoryDiscoveryWorker(_AsyncThread):
    progress = Signal(str)
    categories_found = Signal(object)
    finished = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        request: CategoryDiscoveryRequest,
        *,
        adapter_checker: Callable[[str], bool] = adapter_exists,
        adapter_loader: Callable[[str], Any] = load_adapter,
        engine_factory: Callable[..., Any] = PlaywrightEngine,
        adapter_factory: Callable[..., Any] = YAMLAdapter,
    ) -> None:
        super().__init__()
        self.request = request
        self._adapter_checker = adapter_checker
        self._adapter_loader = adapter_loader
        self._engine_factory = engine_factory
        self._adapter_factory = adapter_factory

    def run(self) -> None:
        try:
            self._execute(self._discover())
        except asyncio.CancelledError:
            self.cancelled.emit()
        except Exception as exc:
            self.error.emit(str(exc))

    async def _discover(self) -> None:
        if not self._adapter_checker(self.request.adapter_file):
            raise FileNotFoundError(f"어댑터 파일이 없습니다: {self.request.adapter_file}")
        model = self._adapter_loader(self.request.adapter_file)
        engine = self._engine_factory(channel=model.adapter.browser.channel, headless=True)
        started = False
        try:
            await engine.start()
            started = True
            adapter = self._adapter_factory(
                adapter=model, engine=engine, supplier_name=self.request.supplier_name,
                supplier_slug=self.request.credential_key,
            )
            categories = await adapter.discover_categories()
            if not self.isInterruptionRequested():
                self.categories_found.emit(categories)
                self.finished.emit(categories)
        finally:
            if started:
                await engine.close()


class CrawlWorker(_AsyncThread):
    progress = Signal(str)
    product_found = Signal(str, str, int)
    finished = Signal(int, int)
    cancelled = Signal(int, int)

    def __init__(
        self,
        request: CrawlRequest,
        *,
        session_factory: Callable[[], Any] = get_session,
        adapter_checker: Callable[[str], bool] = adapter_exists,
        adapter_loader: Callable[[str], Any] = load_adapter,
        engine_factory: Callable[..., Any] = PlaywrightEngine,
        adapter_factory: Callable[..., Any] = YAMLAdapter,
    ) -> None:
        super().__init__()
        self.request = request
        self._session_factory = session_factory
        self._adapter_checker = adapter_checker
        self._adapter_loader = adapter_loader
        self._engine_factory = engine_factory
        self._adapter_factory = adapter_factory
        self._counts = (0, 0)

    def run(self) -> None:
        try:
            self._execute(self._crawl())
        except asyncio.CancelledError:
            self.cancelled.emit(*self._counts)
        except Exception as exc:
            self.error.emit(str(exc))

    async def _crawl(self) -> None:
        request = self.request
        if not self._adapter_checker(request.adapter_file):
            raise FileNotFoundError(f"어댑터 파일이 없습니다: {request.adapter_file}")
        model = self._adapter_loader(request.adapter_file)
        engine = self._engine_factory(channel=model.adapter.browser.channel, headless=True)
        session = self._session_factory()
        run: CrawlRun | None = None
        products = options = 0
        started = False
        try:
            await engine.start()
            started = True
            run = CrawlRun(
                supplier_id=request.supplier_id, run_type="full", status="running",
                started_at=datetime.now(timezone.utc),
                categories_crawled=[path for _, path in request.categories],
            )
            session.add(run)
            session.commit()
            adapter = self._adapter_factory(
                adapter=model, engine=engine, supplier_name=request.supplier_name,
                delay_seconds=request.delay_seconds, supplier_slug=request.credential_key,
            )
            if model.adapter.login.required:
                self.progress.emit("도매처 로그인 중...")
            for category_id, category_path in request.categories:
                self.progress.emit(f"[카테고리] {category_path}")
                async for result in adapter.crawl_category(category_id, request.max_pages):
                    products += 1
                    options += len(result.options)
                    self._counts = products, options
                    self.product_found.emit(
                        result.product.raw_product_name,
                        result.product.supplier_product_code,
                        len(result.options),
                    )
                    self._persist_result(session, run.id, result)
                    if products % 5 == 0:
                        session.commit()
            self._finish_run(session, run, "completed", products, options)
            self.finished.emit(products, options)
        except asyncio.CancelledError:
            if run is not None:
                self._finish_run(session, run, "cancelled", products, options)
            raise
        except Exception as exc:
            if run is not None:
                try:
                    session.rollback()
                    self._finish_run(session, run, "failed", products, options, str(exc))
                except Exception:
                    session.rollback()
            raise
        finally:
            if started:
                await engine.close()
            session.close()

    @staticmethod
    def _finish_run(session, run, status, products, options, error=None) -> None:
        run.status = status
        run.products_crawled = products
        run.options_crawled = options
        run.error = error
        run.finished_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()

    def _persist_result(self, session, crawl_run_id: str, result) -> None:
        data = result.product
        product = session.query(Product).filter_by(
            supplier_id=self.request.supplier_id,
            supplier_product_code=data.supplier_product_code,
        ).first()
        fields = (
            "supplier_name", "supplier_product_id", "supplier_status", "supplier_category",
            "raw_product_name", "origin", "supply_price", "main_image_url",
            "extra_image_urls", "detail_content", "brand_name", "manufacturer",
            "model_name", "raw_metadata",
        )
        if product is None:
            product = Product(
                supplier_id=self.request.supplier_id, crawl_run_id=crawl_run_id,
                supplier_product_code=data.supplier_product_code,
                **{field: getattr(data, field) for field in fields},
            )
            session.add(product)
            session.flush()
        else:
            product.crawl_run_id = crawl_run_id
            for field in fields:
                setattr(product, field, getattr(data, field))
            session.query(ProductOption).filter_by(product_id=product.id).delete()
        for option in result.options:
            values = {
                column.name: getattr(option, column.name)
                for column in ProductOption.__table__.columns
                if column.name not in {"id", "product_id"}
            }
            session.add(ProductOption(product_id=product.id, **values))
