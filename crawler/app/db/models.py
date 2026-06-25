from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    adapter_file: Mapped[str | None] = mapped_column(String, nullable=True)
    needs_login: Mapped[bool] = mapped_column(Boolean, default=False)
    credential_key: Mapped[str | None] = mapped_column(String, nullable=True)
    default_delay_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monitor_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    monitor_interval_hours: Mapped[int] = mapped_column(Integer, default=12)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    crawl_runs: Mapped[list["CrawlRun"]] = relationship(back_populates="supplier", cascade="all, delete-orphan")
    products: Mapped[list["Product"]] = relationship(back_populates="supplier", cascade="all, delete-orphan")


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    run_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    categories_crawled: Mapped[list | None] = mapped_column(JSON, nullable=True)
    products_crawled: Mapped[int] = mapped_column(Integer, default=0)
    options_crawled: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    log: Mapped[list | None] = mapped_column(JSON, nullable=True)

    supplier: Mapped["Supplier"] = relationship(back_populates="crawl_runs")
    products: Mapped[list["Product"]] = relationship(back_populates="crawl_run")
    snapshots: Mapped[list["StockSnapshot"]] = relationship(back_populates="crawl_run")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    crawl_run_id: Mapped[str | None] = mapped_column(ForeignKey("crawl_runs.id", ondelete="SET NULL"), nullable=True)
    supplier_name: Mapped[str] = mapped_column(String, nullable=False)
    supplier_product_code: Mapped[str] = mapped_column(String, nullable=False)
    supplier_product_id: Mapped[str | None] = mapped_column(String, nullable=True)
    supplier_status: Mapped[str] = mapped_column(String, nullable=False)
    supplier_category: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_product_name: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str | None] = mapped_column(String, nullable=True)
    supply_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    main_image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    extra_image_urls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    detail_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    supplier: Mapped["Supplier"] = relationship(back_populates="products")
    crawl_run: Mapped["CrawlRun | None"] = relationship(back_populates="products")
    options: Mapped[list["ProductOption"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    snapshots: Mapped[list["StockSnapshot"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    changes: Mapped[list["StockChange"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductOption(Base):
    __tablename__ = "product_options"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    option_sku: Mapped[str | None] = mapped_column(String, nullable=True)
    option_type: Mapped[str] = mapped_column(String, default="combination")
    option_group_1: Mapped[str | None] = mapped_column(String, nullable=True)
    option_value_1: Mapped[str | None] = mapped_column(String, nullable=True)
    option_group_2: Mapped[str | None] = mapped_column(String, nullable=True)
    option_value_2: Mapped[str | None] = mapped_column(String, nullable=True)
    option_group_3: Mapped[str | None] = mapped_column(String, nullable=True)
    option_value_3: Mapped[str | None] = mapped_column(String, nullable=True)
    option_display_name: Mapped[str] = mapped_column(String, default="")
    option_supply_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    option_sale_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    option_price_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    option_stock_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    option_status: Mapped[str | None] = mapped_column(String, nullable=True)
    option_usable: Mapped[bool] = mapped_column(Boolean, default=True)
    option_main_image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    option_extra_image_urls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    option_position: Mapped[int] = mapped_column(Integer, default=0)
    raw_option_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_option_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="options")


class StockSnapshot(Base):
    __tablename__ = "stock_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    crawl_run_id: Mapped[str | None] = mapped_column(ForeignKey("crawl_runs.id", ondelete="SET NULL"), nullable=True)
    supplier_status: Mapped[str | None] = mapped_column(String, nullable=True)
    supply_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    option_stock_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    product: Mapped["Product"] = relationship(back_populates="snapshots")
    crawl_run: Mapped["CrawlRun | None"] = relationship(back_populates="snapshots")


class StockChange(Base):
    __tablename__ = "stock_changes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    previous_value: Mapped[str | None] = mapped_column(String, nullable=True)
    new_value: Mapped[str | None] = mapped_column(String, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="changes")
