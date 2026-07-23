import uuid
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, JSON, ARRAY, UniqueConstraint, Index, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from database import Base

class Prompt(Base):
    __tablename__ = "prompts"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    template: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

class WholesaleSite(Base):
    __tablename__ = "wholesale_sites"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String)
    homepage_url: Mapped[str | None] = mapped_column(String, nullable=True)
    column_mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # relationship
    products = relationship("Product", back_populates="wholesale_site", cascade="all, delete-orphan")

class ProductImport(Base):
    __tablename__ = "product_imports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    wholesale_site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("wholesale_sites.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    removed_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="pending") # 'pending', 'processing', 'completed', 'failed'
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # relationship
    products = relationship("Product", back_populates="import_run", cascade="all, delete-orphan")


class ProductChangeLog(Base):
    __tablename__ = "product_change_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product_imports.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    wholesale_site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("wholesale_sites.id", ondelete="SET NULL"), nullable=True)

    product_code: Mapped[str | None] = mapped_column(String, nullable=True)
    original_name: Mapped[str] = mapped_column(String)  # snapshot, survives product deletion
    change_type: Mapped[str] = mapped_column(String)  # 'new' | 'updated' | 'removed'
    changed_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    field_changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

class ProcessingTask(Base):
    __tablename__ = "processing_tasks"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # ponytail: retain ownership rows; add TTL cleanup when table growth becomes measurable.

class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    import_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product_imports.id", ondelete="SET NULL"), nullable=True)
    wholesale_site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("wholesale_sites.id", ondelete="SET NULL"), nullable=True)

    product_code: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    wholesale_product_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    price_wholesale: Mapped[int | None] = mapped_column(Integer, nullable=True)
    option_values_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_wholesale_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_retail: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_min_selling: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin: Mapped[str | None] = mapped_column(String, nullable=True)
    options: Mapped[str | None] = mapped_column(Text, nullable=True)
    option_variants: Mapped[list | None] = mapped_column(JSON, nullable=True)
    standard_options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    images_list: Mapped[list | None] = mapped_column(JSON, nullable=True)
    processed_image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    image_processing_status: Mapped[str] = mapped_column(String, default="not_started", nullable=False)
    image_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    wholesale_status: Mapped[str | None] = mapped_column(String, nullable=True)
    wholesale_registered_at: Mapped[str | None] = mapped_column(String, nullable=True)

    original_name: Mapped[str] = mapped_column(String)
    refined_name: Mapped[str | None] = mapped_column(String, nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String, nullable=True)
    keywords: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending") # 'pending', 'processing', 'completed', 'failed'
    warnings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    change_type: Mapped[str | None] = mapped_column(String, nullable=True)
    changed_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    field_changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # relationships
    import_run = relationship("ProductImport", back_populates="products")
    wholesale_site = relationship("WholesaleSite", back_populates="products")
    platform_mappings = relationship("ProductPlatformMapping", back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_products_keywords_gin", "keywords", postgresql_using="gin"),
        Index("idx_products_created_at", "created_at"),
    )

class ProductPlatformMapping(Base):
    __tablename__ = "product_platform_mappings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    platform_name: Mapped[str] = mapped_column(String, index=True) # 'naver', 'coupang', etc.

    category_id: Mapped[str | None] = mapped_column(String, nullable=True)
    category_path: Mapped[str | None] = mapped_column(String, nullable=True)
    product_name: Mapped[str | None] = mapped_column(String, nullable=True)

    platform_product_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sync_status: Mapped[str] = mapped_column(String, default="draft") # 'draft', 'synced', 'failed', 'pending_update'
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    price_changed: Mapped[bool | None] = mapped_column(Boolean, default=False)
    stock_changed: Mapped[bool | None] = mapped_column(Boolean, default=False)
    last_synced_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_synced_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    mapped_attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    product = relationship("Product", back_populates="platform_mappings")

    __table_args__ = (
        UniqueConstraint("product_id", "platform_name", name="uq_product_platform"),
        Index("idx_platform_mappings_search", "platform_name", "sync_status"),
    )
