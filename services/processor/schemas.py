from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, Dict, List, Any, Literal
from uuid import UUID

class ProcessRequest(BaseModel):
    file_id: str
    column_mapping: Dict[str, str]
    llm_provider: Optional[str] = "gemini"
    vision_llm_provider: Optional[str] = "gemini"
    kipris_enabled: Optional[bool] = True
    wholesale_site_id: Optional[UUID] = None
    start_processing: Optional[bool] = True

class PromptBase(BaseModel):
    template: str
    description: Optional[str] = None

class PromptUpdate(BaseModel):
    template: str
    description: Optional[str] = None

class PromptResponse(PromptBase):
    key: str
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- New Extensible DB Product Schemas ---

class ProductPlatformMappingResponse(BaseModel):
    id: UUID
    platform_name: str
    category_id: Optional[str] = None
    category_path: Optional[str] = None
    product_name: Optional[str] = None
    platform_product_id: Optional[str] = None
    sync_status: str
    sync_error: Optional[str] = None
    mapped_attributes: Optional[Any] = None
    price_changed: Optional[bool] = False
    stock_changed: Optional[bool] = False
    last_synced_price: Optional[int] = None
    last_synced_status: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    last_changed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ProductResponse(BaseModel):
    id: UUID
    import_id: Optional[UUID] = None
    wholesale_site_id: Optional[UUID] = None
    product_code: Optional[str] = None
    wholesale_product_id: Optional[str] = None
    price_wholesale: Optional[int] = None
    option_values_raw: Optional[str] = None
    price_wholesale_raw: Optional[str] = None
    price_retail: Optional[int] = None
    price_min_selling: Optional[int] = None
    origin: Optional[str] = None
    options: Optional[str] = None
    option_variants: Optional[List] = None
    standard_options: Optional[List[Dict[str, Any]]] = None
    images_list: Optional[List] = None
    image_detail: Optional[str] = None
    wholesale_status: Optional[str] = None
    wholesale_registered_at: Optional[str] = None
    original_name: str
    refined_name: Optional[str] = None
    brand_name: Optional[str] = None
    keywords: Optional[List[str]] = None
    status: str
    warnings: Optional[Dict] = None
    raw_metadata: Optional[Dict] = None
    processing_time_ms: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    platform_mappings: List[ProductPlatformMappingResponse] = []
    model_config = ConfigDict(from_attributes=True)

class ProductListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: List[ProductResponse]

class ProductImportResponse(BaseModel):
    id: UUID
    filename: str
    total_count: int
    success_count: int
    failed_count: int
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class DBProcessRequest(BaseModel):
    import_id: Optional[UUID] = None
    product_ids: Optional[List[UUID]] = None
    column_mapping: Dict[str, str]
    llm_provider: Optional[str] = "gemini"
    vision_llm_provider: Optional[str] = "gemini"
    kipris_enabled: Optional[bool] = True

# --- Wholesale Site Schemas ---

class WholesaleSiteBase(BaseModel):
    name: str
    homepage_url: Optional[str] = None
    column_mapping: Optional[Dict[str, str]] = None

class WholesaleSiteCreate(WholesaleSiteBase):
    pass

class WholesaleSiteUpdate(WholesaleSiteBase):
    name: Optional[str] = None

class WholesaleSiteResponse(WholesaleSiteBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MarketplaceSnapshotPrice(BaseModel):
    wholesale: Optional[int] = None
    retail: Optional[int] = None
    minimum_selling: Optional[int] = None


class MarketplaceSnapshotImages(BaseModel):
    list: List[str] = []
    detail_content: Optional[str] = None


class MarketplaceSnapshotCategory(BaseModel):
    category_id: Optional[str] = None
    category_path: Optional[str] = None
    product_name: Optional[str] = None
    mapped_attributes: Optional[Any] = None


class MarketplaceSnapshotResponse(BaseModel):
    product_id: UUID
    version: str
    product_code: Optional[str] = None
    wholesale_product_id: Optional[str] = None
    original_name: str
    refined_name: Optional[str] = None
    brand_name: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    origin: Optional[str] = None
    price: MarketplaceSnapshotPrice
    images: MarketplaceSnapshotImages
    options: List[Dict[str, Any]] = []
    standard_options: List[Dict[str, Any]] = []
    market_categories: Dict[str, MarketplaceSnapshotCategory] = {}


class ProductDeleteRequest(BaseModel):
    product_ids: Optional[List[UUID]] = None
    wholesale_site_id: Optional[UUID] = None
    force: bool = False


class ProductDeleteResponse(BaseModel):
    success: bool
    deleted_count: int
    warning_synced_count: int = 0
    message: str


class MarketplaceNameRequest(BaseModel):
    product_ids: List[UUID] = Field(min_length=1)
    marketplace: Literal["smartstore"]
    llm_provider: Literal["openai", "gemini"] = "gemini"


class MarketplaceNameItem(BaseModel):
    product_id: UUID
    original_name: str
    candidates: List[str]
    product_name: str
    generation_method: Literal["llm", "fallback"]
    llm_ms: int
    validation_ms: int
    total_ms: int


class MarketplaceNameResponse(BaseModel):
    generated_count: int
    items: List[MarketplaceNameItem]
    processing_time_ms: int
