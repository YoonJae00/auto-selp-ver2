# Wholesale Site Management, Custom Mapping, and Change Tracking System

## 1. Problem Description
The seller imports product catalogs from various wholesale suppliers (e.g., domeggook, onch, etc.). Each supplier uses a different spreadsheet format (column headers). The platform needed to support:
1. Dynamically storing custom excel layouts per wholesale site.
2. Mapping custom columns (e.g., `도매가`, `공급가격`) to standard database columns (`price_wholesale`, etc.).
3. Implementing a **Smart Upsert** workflow: When an Excel file is re-uploaded containing existing product codes, instead of inserting duplicate product rows, the system updates the core product attributes and detects changes.
4. If a price or stock status change is detected, transition the corresponding platform mapping's status to `'pending_update'` and set tracking flags (`price_changed`, `stock_changed`) so the seller knows exactly which products require synchronization.

## 2. Technical Solution

### A. Database Enhancements
We added a new table `wholesale_sites` and expanded the existing `products` and `product_platform_mappings` tables:

```sql
CREATE TABLE wholesale_sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    name VARCHAR NOT NULL,
    homepage_url VARCHAR,
    column_mapping JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Extended Products with standard attributes:
ALTER TABLE products ADD COLUMN IF NOT EXISTS wholesale_site_id UUID REFERENCES wholesale_sites(id);
ALTER TABLE products ADD COLUMN IF NOT EXISTS product_code VARCHAR;
ALTER TABLE products ADD COLUMN IF NOT EXISTS price_wholesale INTEGER;
ALTER TABLE products ADD COLUMN IF NOT EXISTS price_retail INTEGER;
ALTER TABLE products ADD COLUMN IF NOT EXISTS price_min_selling INTEGER;
ALTER TABLE products ADD COLUMN IF NOT EXISTS origin VARCHAR;
ALTER TABLE products ADD COLUMN IF NOT EXISTS options TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS images_list JSON;
ALTER TABLE products ADD COLUMN IF NOT EXISTS image_detail TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS wholesale_status VARCHAR;

-- Extended ProductPlatformMappings with change tracking flags:
ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS price_changed BOOLEAN DEFAULT FALSE;
ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS stock_changed BOOLEAN DEFAULT FALSE;
ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS last_synced_price INTEGER;
ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS last_synced_status VARCHAR;
ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP;
ALTER TABLE product_platform_mappings ADD COLUMN IF NOT EXISTS last_changed_at TIMESTAMP;
```

### B. TDD Unit Test & Implementation Cycle
1. Developed rigorous tests in `services/processor/tests/test_wholesale.py` defining CRUD operations and smart-upserting logic before writing business code.
2. Implemented the CRUD REST API endpoints inside `main.py` under `/wholesale-sites`.
3. Extended the `/process-db` upload and parsing endpoint to load templates from `WholesaleSite`, parse fields from Excel, find existing products by code, and compute delta updates.
4. Protected sync status to prevent re-processing runs in Celery workers from resetting pending updates back to draft state.
5. All 16 backend unit tests successfully pass.

### C. Premium UI/UX Implementation
1. **Interactive Upload Page (`/upload`)**: Built a card grid of active wholesale sites, a modal to create new sites, a drag-and-drop zone, and a **Visual Column Mapper** that matches Excel headers to system standard properties and saves layout configurations per wholesale site.
2. **Filters & Badges on Products Page (`/products`)**: Enhanced table with inline glassmorphic badges (`가격 변동` and `품절 변동`), filter by wholesale site, filter only update pending items, and a disabled `쇼핑몰 동기화 (예정)` button on the actions toolbar.
3. Exposes direct sidebar access under Layout links.

## 3. Lessons Learned
- **SQLAlchemy Schema Generation**: Since `Base.metadata.create_all` does not apply column alters to existing tables, using custom Raw DDL ALTER TABLE statements in startup seed prompts and test suite fixtures guarantees zero schema synchronization failures.
- **Smart Status Preservation**: Wrapping state initializations during Celery runs prevents pipeline refreshes from wiping user-facing update tracking statuses.
- **TypeScript Interface Extension**: Ensuring client interfaces (`PlatformMapping`) mirror backend extensions keeps React compilations fully type-safe.
