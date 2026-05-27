import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from database import Base


class MarketAccount(Base):
    __tablename__ = "market_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    market_code: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    connection_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="connected"
    )
    is_primary: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    settings: Mapped["MarketAccountSettings"] = relationship(
        back_populates="market_account",
        cascade="all, delete-orphan",
        uselist=False,
    )
    drafts: Mapped[list["MarketListingDraft"]] = relationship(
        back_populates="market_account",
        passive_deletes=True,
    )


class MarketAccountSettings(Base):
    __tablename__ = "market_account_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    market_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("market_accounts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    settings_schema_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="v1"
    )
    connection_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fulfillment_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    claim_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    listing_defaults: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generation_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    market_account: Mapped[MarketAccount] = relationship(back_populates="settings")


class MarketDraftGenerationJob(Base):
    __tablename__ = "market_draft_generation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    source_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    requested_source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_source_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MarketListingDraft(Base):
    __tablename__ = "market_listing_drafts"
    __table_args__ = (
        Index(
            "uq_market_listing_drafts_active",
            "source_product_id",
            "market_account_id",
            "draft_kind",
            unique=True,
            postgresql_where=text(
                "status IN ('generated', 'needs_review', 'ready', 'submitting', 'failed')"
            ),
        ),
        Index("ix_market_listing_drafts_market_account_id", "market_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    source_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    source_product_version: Mapped[str] = mapped_column(String(100), nullable=False)
    market_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("market_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    market_code: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    draft_kind: Mapped[str] = mapped_column(String(50), nullable=False, default="create")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="generated")
    display_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sale_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_profit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_margin_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    primary_image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    override_patch: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_result: Mapped[dict] = mapped_column(JSON, nullable=False)
    recipe_versions: Mapped[dict] = mapped_column(JSON, nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(100), nullable=False)
    remote_product_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    market_account: Mapped[MarketAccount] = relationship(back_populates="drafts")
