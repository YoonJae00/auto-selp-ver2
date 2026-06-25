# Wholesale Crawler Design Spec

Date: 2026-06-21

## 1. Goal

Build a cross-platform desktop crawler application that collects product data from wholesale supplier websites when no Excel product ledger is provided, normalizes scraped data into Auto-Selp's standard product schema (`products` + `product_options`), monitors stock status changes over time, and exports results in a format ready for the existing `/upload` pipeline.

The crawler is an independent Python package living at `crawler/` in the repository root, separate from the existing FastAPI services. It shares the standard schema field definitions but does not import service code directly, so it can run standalone on end-user machines without the full backend stack.

## 2. Tech Stack

- Python 3.11+
- PySide6 (Qt for Python) — cross-platform desktop GUI
- Playwright for Python — browser automation, using system Edge/Chrome (`channel="msedge"` / `channel="chrome"`) first, falling back to Playwright bundled Chromium
- SQLAlchemy + SQLite — local storage for suppliers, crawl runs, products, options, snapshots
- keyring — OS-native credential storage (Windows Credential Manager, macOS Keychain)
- APScheduler — periodic stock monitoring jobs
- openpyxl — Excel export matching the standard schema
- google-generativeai / openai — LLM for new-site adapter generation (Gemini 3.1 Flash Lite default, GPT fallback)
- platformdirs — OS-specific data/config/cache directories
- PyInstaller + Inno Setup — Windows installer packaging
- Pygments — YAML syntax highlighting in the adapter editor

## 3. Cross-Platform Requirements

- Windows is the primary end-user platform. macOS is the developer platform.
- All paths use `pathlib.Path` and `platformdirs` for OS-specific directories:
  - Windows: `%APPDATA%/auto-selp-crawler/`
  - macOS: `~/Library/Application Support/auto-selp-crawler/`
- `main.py` forces UTF-8 stdout/stderr encoding to avoid Korean encoding issues on Windows.
- PyInstaller builds with `--windowed` to hide the console on Windows.
- No admin privileges required — all writes go to user directories.

## 4. Folder Structure

```
crawler/
├── README.md
├── requirements.txt
├── requirements-dev.txt
├── build_windows.spec
├── installer.iss
├── main.py
├── app/
│   ├── app.py
│   ├── config.py
│   ├── paths.py
│   ├── schema/
│   │   └── standard.py
│   ├── db/
│   │   ├── models.py
│   │   └── session.py
│   ├── credentials/
│   │   └── store.py
│   ├── crawlers/
│   │   ├── base.py
│   │   ├── engine.py
│   │   ├── registry.py
│   │   └── adapters/
│   ├── analyzer/
│   │   ├── site_probe.py
│   │   ├── html_reducer.py
│   │   ├── llm_client.py
│   │   ├── adapter_generator.py
│   │   └── adapter_schema.py
│   ├── monitor/
│   │   ├── scheduler.py
│   │   └── stock_checker.py
│   ├── exporters/
│   │   ├── excel.py
│   │   └── server_client.py
│   ├── update/
│   │   └── checker.py
│   └── ui/
│       ├── main_window.py
│       ├── first_run_wizard.py
│       ├── tabs/
│       │   ├── suppliers_tab.py
│       │   ├── adapter_builder_tab.py
│       │   ├── crawl_tab.py
│       │   ├── monitor_tab.py
│       │   ├── export_tab.py
│       │   └── settings_tab.py
│       └── styles/
├── assets/
│   ├── icon.ico
│   ├── icon.icns
│   └── icon.png
├── adapters_data/
├── data/
└── tests/
```

## 5. Data Model

### `suppliers`
- `id`: UUID primary key
- `name`: supplier display name
- `base_url`: supplier website root
- `adapter_file`: YAML filename under `adapters_data/`
- `needs_login`: boolean
- `credential_key`: keyring service identifier (credentials stored in OS keychain, never in DB)
- `default_delay_seconds`: per-supplier crawl delay override (null = use global setting)
- `monitor_enabled`: boolean
- `monitor_interval_hours`: integer (6, 12, 24)
- `created_at`, `updated_at`: timestamps

### `crawl_runs`
- `id`: UUID primary key
- `supplier_id`: foreign key
- `run_type`: `full` (all fields) or `stock_check` (status/stock/price only)
- `status`: `pending`, `running`, `completed`, `failed`
- `categories_crawled`: JSON list of category paths
- `products_crawled`: integer count
- `options_crawled`: integer count
- `started_at`, `finished_at`: timestamps
- `error`: nullable error message
- `log`: JSON array of log entries

### `products`
- `id`: UUID primary key
- `supplier_id`: foreign key
- `crawl_run_id`: foreign key (last run that updated this product)
- `supplier_product_code`: standard schema join key, unique per supplier
- `supplier_product_id`: standard schema field
- `supplier_name`: standard schema field
- `supplier_status`: standard schema field (`available`, `sold_out`, `stopped`)
- `supplier_category`: category path string, e.g. `여성의류 > 티셔츠 > 반팔`
- `raw_product_name`: standard schema field
- `origin`: standard schema field
- `supply_price`: integer
- `main_image_url`: string
- `extra_image_urls`: JSON array
- `detail_content`: text (HTML)
- `brand_name`, `manufacturer`, `model_name`: optional standard fields
- `raw_metadata`: JSON copy of all scraped fields
- `first_seen_at`, `last_seen_at`: timestamps

### `product_options`
- `id`: UUID primary key
- `product_id`: foreign key
- `option_sku`: standard schema field
- `option_type`: `single`, `combination`, `custom`, `standard`
- `option_group_1`, `option_value_1`: first option group
- `option_group_2`, `option_value_2`: second option group (dependent option support)
- `option_group_3`, `option_value_3`: third option group
- `option_display_name`: derived display name
- `option_supply_price`: integer
- `option_sale_price`: nullable integer
- `option_price_delta`: derived integer
- `option_stock_quantity`: nullable integer
- `option_status`: string
- `option_usable`: boolean
- `option_main_image_url`, `option_extra_image_urls`: image fields
- `option_position`: integer sort key
- `raw_option_text`, `raw_option_metadata`: preserved raw data

### `stock_snapshots`
- `id`: UUID primary key
- `product_id`: foreign key
- `crawl_run_id`: foreign key
- `supplier_status`: status at snapshot time
- `supply_price`: price at snapshot time
- `option_stock_json`: JSON map of option SKU → stock quantity
- `captured_at`: timestamp

### `stock_changes`
- `id`: UUID primary key
- `product_id`: foreign key
- `change_type`: `sold_out`, `restocked`, `price_changed`, `stock_changed`
- `previous_value`, `new_value`: strings
- `detected_at`: timestamp
- `acknowledged`: boolean (read status for dashboard badge)
- `acknowledged_at`: nullable timestamp

## 6. Standard Schema Mapping

The crawler copies the field definitions from `services/processor/utils/standard_product_schema.py` into `app/schema/standard.py` with a header comment pointing to the original. This keeps the crawler standalone while preserving field compatibility.

Every scraped product is normalized into the same field names used by the existing wholesale upload pipeline, so exported Excel files can be uploaded through the existing `/upload` page without any mapping step.

## 7. Adapter System

### 7.1 Adapter YAML Schema

Each supplier has a YAML file under `adapters_data/` describing how to crawl that site. The schema covers:

```yaml
adapter:
  name: string
  base_url: string
  encoding: utf-8 | euc-kr

  browser:
    channel: msedge | chrome | chromium
    user_agent: default | custom string
    wait_until: networkidle | domcontentloaded
    navigation_timeout: integer (ms)

  login:
    required: boolean
    login_url: string
    fields:
      id: CSS selector
      password: CSS selector
    submit: CSS selector
    success_indicator: CSS selector
    failure_indicator: CSS selector

  categories:
    mode: all_products | tree | hybrid
    all_products:
      available: boolean
      url: string
    navigation:
      menu_selector: string
      link_selector: string
      name_source: text | attribute
      url_attribute: string
      max_depth: integer (1-3)
      submenu:
        selector: string
        expand_trigger: hover | click | static
    url_template: string with {category_id} and {page}
    store_category_path: boolean

  listing:
    pagination:
      type: page_number | next_button | infinite_scroll
      page_param: string
      start: integer
      max_pages: integer
      stop_indicator: CSS selector
    product_link:
      selector: string
      attribute: href
      base: relative | absolute

  product:
    supplier_product_id:
      selector: string
      transform: strip | extract_number
    supplier_product_code:
      selector: string
      transform: strip
      fallback_from: url | null
    raw_product_name:
      selector: string
    supplier_status:
      selector: string
      mapping:
        "판매중": available
        "정상": available
        "품절": sold_out
        "판매중지": stopped
      default: available
    supply_price:
      selector: string
      transform: extract_number
    origin:
      selector: string
      fallback: string
    main_image_url:
      selector: string
      attribute: src
      fallback_attribute: data-src
    detail_content:
      selector: string
      html: true
    extra_image_urls:
      selector: string
      attribute: src
      multiple: true
    brand_name:
      selector: string
      optional: true

  options:
    detection: dom | ajax | none
    type: combination | single | custom
    groups:
      - name: string
        group_label_selector: string
        values_selector: string
        value_text: text | value | attribute
        value_attribute: string
    dependent_options:
      enabled: boolean
      level_1_group: string
      level_2_group: string
      level_2_trigger: click | select
      level_2_load_indicator: CSS selector
      level_2_values_selector: string
    option_image_url:
      selector: string
      attribute: src
      optional: true
    option_price_delta:
      selector: string
      transform: extract_signed_number
    ajax_option:
      enabled: boolean
      endpoint_pattern: string
      response_path: string

  delays:
    between_pages: integer (seconds, override)
    between_products: integer (seconds, override)
```

### 7.2 Adapter Crawler Flow

1. Load adapter YAML, validate with pydantic schema.
2. Launch Playwright with the configured browser channel.
3. If `login.required`, load credentials from keyring, perform login sequence, verify success indicator.
4. Resolve categories to crawl:
   - `all_products` mode: use the single all-products URL.
   - `tree` mode: walk the navigation menu up to `max_depth`, collect category entries.
   - `hybrid` mode: respect user selection from the crawl tab.
5. For each selected category, paginate through the listing:
   - Build URL from `url_template`.
   - Extract product links via `product_link.selector`.
   - Stop when `stop_indicator` appears or `max_pages` reached.
6. For each product detail page:
   - Extract all standard fields using configured selectors.
   - Extract options:
     - Independent options: read all values from `groups[].values_selector`.
     - Dependent options: for each level-1 value, trigger the level-2 load (click/select), wait for `level_2_load_indicator` to detach, read level-2 values, build all combinations.
   - Normalize into standard option rows with `option_group_1`, `option_value_1`, `option_group_2`, `option_value_2`.
7. Apply delay between pages/products (global setting or per-supplier override).
8. Save products and options to SQLite, emit progress signals to the UI.

### 7.3 New-Site Analysis Pipeline

When a user adds a new supplier without an existing adapter:

1. **Site Probe** (`analyzer/site_probe.py`):
   - User enters the supplier name, main URL, and optionally a sample listing/detail URL.
   - Playwright navigates to the main page and detects:
     - Final URL after redirects, page encoding.
     - Whether a login form is present.
     - Category navigation structure (menu selectors, submenu expand trigger, depth).
     - Whether an "all products" menu exists.
   - Playwright navigates to the sample listing URL (or first detected category) and captures:
     - Reduced listing HTML.
     - Sample product links.
     - Pagination structure.
   - Playwright follows the first product link and captures the reduced detail HTML.
   - Network requests are logged to detect AJAX option loading.

2. **HTML Reduction** (`analyzer/html_reducer.py`):
   - Remove `<script>`, `<style>`, `<svg>`, comments, inline styles, tracking pixels.
   - Keep tag structure, class, id, data-* attributes, and the first 80 characters of text content.
   - Compress repeated product card patterns to the first 2 occurrences plus a count comment.
   - Target: each HTML snippet under 15K tokens.

3. **LLM Adapter Generation** (`analyzer/adapter_generator.py`):
   - Default provider: Gemini 3.1 Flash Lite (low cost, large context).
   - Fallback provider: GPT-5.2 if Gemini output fails validation twice.
   - Prompt includes:
     - The standard schema field list.
     - Reduced listing HTML and detail HTML.
     - AJAX request patterns.
     - Two example adapter YAMLs as 2-shot guidance.
     - Strict instruction to output only YAML.
   - Output is parsed with `yaml.safe_load`, validated against the pydantic adapter schema, and CSS selectors are syntax-checked.

4. **User Validation** (`ui/tabs/adapter_builder_tab.py`):
   - The generated YAML opens in a `QPlainTextEdit` with Pygments YAML highlighting.
   - A side panel lists every standard field with a "Test" button.
   - Single-field test: applies that selector to the sample detail page and shows the extracted value.
   - Full-field test: runs all fields and highlights failures.
   - Three-sample test: picks 3 random products from the listing and verifies consistency.
   - Option test: runs the option extraction logic and shows group/value/price/image mappings.
   - Pagination test: builds the page-2 URL and verifies products load.
   - Login test: if login is required, runs the login sequence with stored credentials.
   - Failed fields can be sent back to the LLM with the error message for a retry.
   - The user can also manually edit the YAML at any time.
   - On "Save", the YAML is written to `adapters_data/{supplier_slug}.yaml` with a backup of any existing file.

## 8. Crawl Execution UI

The crawl tab lets the user:

1. Select a supplier from a dropdown.
2. View the discovered category tree as a tri-state checkbox list:
   - If `all_products` is available, a top-level "전체 상품" checkbox appears.
   - Categories show product counts where detected.
   - Checking a parent checks all children.
3. Set the max pages per category (default from adapter, override per run).
4. Set a temporary delay override for this run.
5. Start crawling. A QThread runs the crawler engine and emits progress signals:
   - Current category (e.g. `[2/5] 여성의류 > 티셔츠`).
   - Current page and product count.
   - Log lines in real time.
6. Pause/resume is not supported in the first version; the user can cancel, and the next run restarts from page 1 of each category. A future version may add resume from last position.
7. On completion, show a summary (categories crawled, products extracted, options extracted, duration) and a preview table of the first 50 products.

## 9. Stock Monitoring Pipeline

### 9.1 Scheduler

APScheduler runs inside the GUI process. Each supplier with `monitor_enabled=true` has a scheduled job at `monitor_interval_hours`. The user can also trigger a manual stock check from the monitor tab.

### 9.2 Lightweight Stock Check

A stock check crawl is faster than a full crawl because it only extracts:
- `supplier_status`
- `supply_price`
- `option_stock_quantity` for each option

It reuses the same adapter YAML but skips fields not needed for status comparison. If the adapter's listing page exposes status badges, the stock check can read the listing directly without visiting every detail page. Otherwise, it visits detail pages but only extracts the status/price/stock selectors.

### 9.3 Change Detection

`stock_checker.py` compares the new snapshot against the most recent previous snapshot for each product:

| Previous | New | Change type |
| --- | --- | --- |
| available | sold_out | `sold_out` |
| sold_out | available | `restocked` |
| any | any (price differs) | `price_changed` |
| any | any (option stock differs) | `stock_changed` |

Each change is recorded in `stock_changes` with `acknowledged=false`. The monitor tab badge shows the count of unacknowledged changes.

### 9.4 Monitor Dashboard

The monitor tab shows:
- Unacknowledged change count badge.
- A filterable table: time, supplier, product, change type, previous value, new value.
- Filters: supplier, change type, date range.
- "Acknowledge" action to mark changes as read.
- Per-supplier monitor enable toggle and interval selector.

## 10. Export

### 10.1 Excel Export

`exporters/excel.py` writes a workbook with two sheets matching the standard schema:

- `products` sheet: one row per product with all standard product columns.
- `product_options` sheet: zero or more rows per product with all standard option columns.

This file is directly uploadable through the existing `/upload` page in the Auto-Selp frontend, connecting the crawler to the existing processing pipeline without any backend changes.

### 10.2 Server Sync (Phase 2 interface only)

`exporters/server_client.py` defines an interface for pushing products directly to the processor service API. The first version implements only the Excel export. The server sync method signature is defined but raises `NotImplementedError`, leaving the hook open for the future auto-sync feature.

## 11. Settings

The settings tab covers:

- **LLM provider**: OpenAI or Gemini.
- **LLM API key**: stored in keyring, never written to disk in plaintext.
- **Browser channel**: `msedge` (default), `chrome`, or `chromium`.
- **Global crawl delay**: default 0 seconds, range 0-10 seconds. Applies to both between-pages and between-products delays unless a supplier has a per-supplier override.
- **Update check**: button to check GitHub Releases for a newer version; on update found, shows a notification with a download link. No automatic download or install.
- **Data directory**: read-only display of the platformdirs path.

## 12. Credential Handling

- Supplier login credentials (ID/password) are stored in the OS keyring under a service name like `auto-selp-crawler.{supplier_slug}`.
- LLM API keys are stored in the OS keyring under `auto-selp-crawler.llm`.
- The SQLite database stores only a `credential_key` string referencing the keyring entry, never the credential itself.
- Credentials are never written to YAML adapter files, source code, documentation, or git commits.
- The first-run wizard prompts the user to enter their LLM API key and optionally configure browser settings.

## 13. Windows Packaging

### 13.1 PyInstaller

`build_windows.spec` builds an onedir, windowed application:
- Entry point: `main.py`
- Hidden imports for PySide6, Playwright, keyring backends, APScheduler, pydantic.
- Include `assets/icon.ico` as the application icon.
- Exclude unittests, pytest, documentation.
- The resulting `dist/AutoSelpCrawler/` directory is the input for the installer.

### 13.2 Inno Setup

`installer.iss` produces `AutoSelpCrawler-Setup-x.y.z.exe`:
- Installs to `%LOCALAPPDATA%/Programs/AutoSelpCrawler` (no admin required).
- Creates Start Menu shortcut and optional desktop shortcut.
- Registers uninstaller in Add/Remove Programs.
- Does not bundle Playwright browsers; the app uses system Edge/Chrome at runtime.
- File associations and auto-update are out of scope.

### 13.3 GitHub Actions

`.github/workflows/build_windows.yml` (inside `crawler/`):
- Triggers on version tags (`v*`).
- Runs on `windows-latest`.
- Installs Python 3.11, dependencies, runs tests.
- Runs PyInstaller, then Inno Setup.
- Uploads the installer as a GitHub Release asset.

## 14. Testing

Backend/logic tests should cover:

- Standard schema field normalization from scraped values.
- HTML reducer output size and structure preservation.
- LLM YAML output parsing and validation.
- Adapter YAML loading and pydantic validation.
- Category discovery for tree, all_products, and hybrid modes.
- Independent and dependent option extraction.
- Stock snapshot comparison and change detection.
- Excel export field mapping and sheet structure.
- Credential store save/load with keyring mock.
- Path resolution on Windows-style and macOS-style paths.

UI tests are deferred in the first version; manual testing against the itopic sample site is the primary validation path.

## 15. Out Of Scope

- Automatic background app updates.
- Code signing for the Windows installer.
- macOS `.app` bundle packaging.
- Anti-bot evasion beyond configurable delays and user agents.
- Three-level dependent options (only two levels: color → size).
- Resume crawling from the last position after cancellation.
- Real-time push notifications (email, Slack, etc.).
- Direct processor server sync implementation (interface only).
- Marketplace-specific export formats (the existing pipeline handles that after upload).
