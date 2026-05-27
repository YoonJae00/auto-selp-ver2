import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MarketAccountCreate(BaseModel):
    market_code: str
    display_name: str
    credentials: dict[str, str]


class MarketAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    market_code: str
    display_name: str
    connection_status: str
    is_primary: bool
    created_at: datetime
    updated_at: datetime


class MarketAccountSettingsUpdate(BaseModel):
    settings_schema_version: str = "v1"
    connection_config: dict | None = None
    fulfillment_config: dict | None = None
    claim_config: dict | None = None
    listing_defaults: dict | None = None
    generation_rules: dict | None = None


class MarketAccountSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    market_account_id: uuid.UUID
    settings_schema_version: str
    connection_config: dict | None
    fulfillment_config: dict | None
    claim_config: dict | None
    listing_defaults: dict | None
    generation_rules: dict | None
    created_at: datetime
    updated_at: datetime


class DraftResult(BaseModel):
    display_title: str | None = None
    category_id: str | None = None
    sale_price: int | None = None
    cost_price: int | None = None
    expected_profit: int | None = None
    expected_margin_rate: float | None = None
    primary_image_url: str | None = None
    generated_payload: dict[str, Any] = Field(default_factory=dict)
    validation_result: dict[str, Any] = Field(default_factory=dict)
    adapter_version: str
    recipe_versions: dict[str, str] = Field(default_factory=dict)
