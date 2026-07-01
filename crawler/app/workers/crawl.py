from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from app.crawlers.engine import PlaywrightEngine
from app.crawlers.registry import adapter_exists, load_adapter
from app.crawlers.yaml_adapter import YAMLAdapter
from app.db.models import CrawlRun, Product, ProductOption
from app.db.session import get_session
from app.diagnostics import log_exception, sanitize_diagnostic


logger = logging.getLogger(__name__)


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
            logger.info("category discovery cancelled supplier=%s", self.request.supplier_name)
            self.cancelled.emit()
        except Exception as exc:
            log_exception(logger, f"category discovery failed supplier={self.request.supplier_name}", exc)
            self.error.emit(str(exc))

    async def _discover(self) -> None:
        engine = None
        categories = None
        try:
            logger.info(
                "category discovery started supplier=%s adapter=%s",
                self.request.supplier_name,
                self.request.adapter_file,
            )
            if not self._adapter_checker(self.request.adapter_file):
                raise FileNotFoundError(f"어댑터 파일이 없습니다: {self.request.adapter_file}")
            model = self._adapter_loader(self.request.adapter_file)
            engine = self._engine_factory(channel=model.adapter.browser.channel, headless=True)
            await engine.start()
            adapter = self._adapter_factory(
                adapter=model, engine=engine, supplier_name=self.request.supplier_name,
                supplier_slug=self.request.credential_key,
            )
            categories = await adapter.discover_categories()
        finally:
            if engine is not None:
                await engine.close()
        if not self.isInterruptionRequested() and categories is not None:
            logger.info(
                "category discovery completed supplier=%s categories=%d",
                self.request.supplier_name,
                len(categories),
            )
            self.categories_found.emit(categories)
            self.finished.emit(categories)


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
            logger.info("crawl cancelled supplier=%s products=%d options=%d", self.request.supplier_name, *self._counts)
            self.cancelled.emit(*self._counts)
        except Exception as exc:
            log_exception(logger, f"crawl failed supplier={self.request.supplier_name}", exc)
            self.error.emit(str(exc))

    async def _crawl(self) -> None:
        request = self.request
        session = self._session_factory()
        run = None
        products = options = 0
        engine = None
        try:
            logger.info(
                "crawl started supplier=%s adapter=%s categories=%d max_pages=%d delay=%d",
                request.supplier_name,
                request.adapter_file,
                len(request.categories),
                request.max_pages,
                request.delay_seconds,
            )
            run = CrawlRun(
                supplier_id=request.supplier_id, run_type="full", status="running",
                started_at=datetime.now(timezone.utc),
                categories_crawled=[path for _, path in request.categories],
            )
            session.add(run)
            session.commit()
            if not self._adapter_checker(request.adapter_file):
                raise FileNotFoundError(f"어댑터 파일이 없습니다: {request.adapter_file}")
            model = self._adapter_loader(request.adapter_file)
            engine = self._engine_factory(channel=model.adapter.browser.channel, headless=True)
            await engine.start()
            adapter = self._adapter_factory(
                adapter=model, engine=engine, supplier_name=request.supplier_name,
                delay_seconds=request.delay_seconds, supplier_slug=request.credential_key,
            )
            if model.adapter.login.required:
                logger.info("crawl login required supplier=%s", request.supplier_name)
                self.progress.emit("도매처 로그인 중...")
            for category_id, category_path in request.categories:
                logger.info("crawl category started supplier=%s category=%s", request.supplier_name, category_path)
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
                    self.progress.emit(
                        f"상품 {products}: {result.product.raw_product_name} "
                        f"({result.product.supplier_product_code})"
                    )
                    self._persist_result(session, run.id, result)
                    if products % 5 == 0:
                        session.commit()
                logger.info("crawl category completed supplier=%s category=%s products=%d", request.supplier_name, category_path, products)
            await engine.close()
            engine = None
            self._finish_run(session, run, "completed", products, options)
            logger.info("crawl completed supplier=%s products=%d options=%d", request.supplier_name, products, options)
            self.finished.emit(products, options)
        except asyncio.CancelledError:
            try:
                if engine is not None:
                    await engine.close()
                    engine = None
            except Exception as exc:
                safe = sanitize_diagnostic(exc)
                session.rollback()
                if run is not None:
                    self._finish_run(session, run, "failed", products, options, safe)
                raise RuntimeError(safe) from exc
            if run is not None:
                self._finish_run(session, run, "cancelled", products, options)
            raise
        except Exception as exc:
            safe = sanitize_diagnostic(exc)
            log_exception(logger, f"crawl exception supplier={request.supplier_name}", exc)
            if engine is not None:
                try:
                    await engine.close()
                    engine = None
                except Exception as close_exc:
                    safe = f"{safe}; 종료 오류: {sanitize_diagnostic(close_exc)}"
            session.rollback()
            if run is not None:
                try:
                    self._finish_run(session, run, "failed", products, options, safe)
                except Exception:
                    session.rollback()
            raise RuntimeError(safe) from exc
        finally:
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
