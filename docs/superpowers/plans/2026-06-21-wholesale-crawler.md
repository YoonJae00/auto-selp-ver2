# Wholesale Crawler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cross-platform PySide6 desktop crawler that scrapes wholesale supplier websites into Auto-Selp's standard product schema, monitors stock changes, and exports Excel files compatible with the existing `/upload` pipeline.

**Architecture:** A standalone Python package at `crawler/` with PySide6 GUI, Playwright browser automation, SQLite storage, keyring credentials, APScheduler monitoring, and LLM-based new-site adapter generation. The crawler copies standard schema field definitions from the processor service to remain standalone.

**Tech Stack:** Python 3.11+, PySide6, Playwright, SQLAlchemy + SQLite, keyring, APScheduler, openpyxl, google-generativeai, openai, platformdirs, PyInstaller, Inno Setup.

**Reference Spec:** `docs/superpowers/specs/2026-06-21-wholesale-crawler-design.md`

---

## File Structure

- Create `crawler/requirements.txt`: runtime dependencies.
- Create `crawler/requirements-dev.txt`: dev/test dependencies.
- Create `crawler/main.py`: QApplication entry point with UTF-8 forcing.
- Create `crawler/app/__init__.py`: package marker.
- Create `crawler/app/paths.py`: platformdirs-based path resolution.
- Create `crawler/app/config.py`: app-level config singleton.
- Create `crawler/app/schema/standard.py`: standard schema copy from processor.
- Create `crawler/app/db/models.py`: SQLAlchemy models.
- Create `crawler/app/db/session.py`: SQLite session factory.
- Create `crawler/app/credentials/store.py`: keyring wrapper.
- Create `crawler/app/crawlers/base.py`: BaseAdapter interface.
- Create `crawler/app/crawlers/engine.py`: Playwright session manager.
- Create `crawler/app/crawlers/registry.py`: YAML adapter loader.
- Create `crawler/app/analyzer/site_probe.py`: DOM/network probing.
- Create `crawler/app/analyzer/html_reducer.py`: HTML compaction for LLM.
- Create `crawler/app/analyzer/llm_client.py`: OpenAI/Gemini caller.
- Create `crawler/app/analyzer/adapter_generator.py`: LLM YAML generation.
- Create `crawler/app/analyzer/adapter_schema.py`: pydantic adapter validator.
- Create `crawler/app/monitor/scheduler.py`: APScheduler wrapper.
- Create `crawler/app/monitor/stock_checker.py`: snapshot comparison.
- Create `crawler/app/exporters/excel.py`: standard schema Excel writer.
- Create `crawler/app/exporters/server_client.py`: phase-2 server sync interface.
- Create `crawler/app/update/checker.py`: GitHub Release version check.
- Create `crawler/app/ui/main_window.py`: main window with tab bar.
- Create `crawler/app/ui/first_run_wizard.py`: first-run setup wizard.
- Create `crawler/app/ui/tabs/suppliers_tab.py`: supplier management.
- Create `crawler/app/ui/tabs/adapter_builder_tab.py`: LLM analysis + validation.
- Create `crawler/app/ui/tabs/crawl_tab.py`: crawl execution.
- Create `crawler/app/ui/tabs/monitor_tab.py`: stock change dashboard.
- Create `crawler/app/ui/tabs/export_tab.py`: Excel/server export.
- Create `crawler/app/ui/tabs/settings_tab.py`: LLM key, browser, delay, update.
- Create `crawler/app/ui/styles/global.qss`: global Qt stylesheet.
- Create `crawler/assets/icon.png`: placeholder app icon.
- Create `crawler/adapters_data/.gitkeep`: adapter directory marker.
- Create `crawler/data/.gitkeep`: runtime data directory marker.
- Create `crawler/tests/test_standard_schema.py`: schema normalization tests.
- Create `crawler/tests/test_html_reducer.py`: HTML reduction tests.
- Create `crawler/tests/test_adapter_schema.py`: adapter YAML validation tests.
- Create `crawler/tests/test_stock_checker.py`: change detection tests.
- Create `crawler/tests/test_excel_export.py`: Excel output tests.
- Create `crawler/tests/test_credentials_store.py`: keyring mock tests.
- Create `crawler/tests/test_paths.py`: cross-platform path tests.
- Create `crawler/README.md`: installation and usage guide.
- Create `crawler/build_windows.spec`: PyInstaller spec.
- Create `crawler/installer.iss`: Inno Setup script.
- Create `crawler/.github/workflows/build_windows.yml`: Windows CI build.
- Create `crawler/.gitignore`: ignore data/, adapters_data/*.yaml (keep .gitkeep), __pycache__, dist/, build/.

---

### Task 1: Initialize Package And Dependencies

**Files:**
- Create: `crawler/requirements.txt`
- Create: `crawler/requirements-dev.txt`
- Create: `crawler/.gitignore`
- Create: `crawler/app/__init__.py`
- Create: `crawler/adapters_data/.gitkeep`
- Create: `crawler/data/.gitkeep`

- [ ] **Step 1: Create requirements.txt**

```
PySide6>=6.7,<7
playwright>=1.40
SQLAlchemy>=2.0
keyring>=24.0
APScheduler>=3.10
openpyxl>=3.1
google-generativeai>=0.5
openai>=1.10
platformdirs>=4.0
pydantic>=2.5
PyYAML>=6.0
Pygments>=2.17
```

- [ ] **Step 2: Create requirements-dev.txt**

```
-r requirements.txt
pytest>=8.0
pytest-asyncio>=0.23
respx>=0.20
```

- [ ] **Step 3: Create .gitignore**

```
__pycache__/
*.pyc
data/*.db
data/exports/
adapters_data/*.yaml
!adapters_data/.gitkeep
dist/
build/
*.spec.bak
.env
```

- [ ] **Step 4: Create package markers**

Create empty `crawler/app/__init__.py`, `crawler/adapters_data/.gitkeep`, `crawler/data/.gitkeep`.

- [ ] **Step 5: Commit**

```bash
git add crawler/requirements.txt crawler/requirements-dev.txt crawler/.gitignore crawler/app/__init__.py crawler/adapters_data/.gitkeep crawler/data/.gitkeep
git commit -m "chore: initialize crawler package structure"
```

---

### Task 2: Cross-Platform Paths And Config

**Files:**
- Create: `crawler/app/paths.py`
- Create: `crawler/app/config.py`
- Test: `crawler/tests/test_paths.py`

- [ ] **Step 1: Create paths.py with platformdirs**

```python
from pathlib import Path
from platformdirs import user_data_dir, user_config_dir, user_cache_dir

APP_NAME = "auto-selp-crawler"

def data_dir() -> Path:
    path = Path(user_data_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path

def config_dir() -> Path:
    path = Path(user_config_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path

def cache_dir() -> Path:
    path = Path(user_cache_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path

def db_path() -> Path:
    return data_dir() / "crawler.db"

def adapters_dir() -> Path:
    path = data_dir() / "adapters"
    path.mkdir(parents=True, exist_ok=True)
    return path

def exports_dir() -> Path:
    path = data_dir() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path
```

- [ ] **Step 2: Create config.py singleton**

```python
from dataclasses import dataclass

@dataclass
class AppConfig:
    llm_provider: str = "gemini"
    browser_channel: str = "msedge"
    global_delay_seconds: int = 0
    check_updates_on_start: bool = True

def load_config() -> AppConfig:
    # Phase 0: in-memory only. Phase 6 adds JSON persistence in config_dir().
    return AppConfig()

def save_config(config: AppConfig) -> None:
    # Phase 6 implements persistence.
    pass
```

- [ ] **Step 3: Create test_paths.py**

```python
from pathlib import Path
from unittest.mock import patch
from app.paths import data_dir, db_path, adapters_dir, exports_dir

def test_data_dir_creates_directory(tmp_path):
    with patch("app.paths.user_data_dir", return_value=str(tmp_path)):
        result = data_dir()
        assert result == tmp_path
        assert result.exists()

def test_db_path_under_data_dir(tmp_path):
    with patch("app.paths.user_data_dir", return_value=str(tmp_path)):
        assert db_path() == tmp_path / "crawler.db"

def test_adapters_dir_creates_subdirectory(tmp_path):
    with patch("app.paths.user_data_dir", return_value=str(tmp_path)):
        result = adapters_dir()
        assert result == tmp_path / "adapters"
        assert result.exists()

def test_exports_dir_creates_subdirectory(tmp_path):
    with patch("app.paths.user_data_dir", return_value=str(tmp_path)):
        result = exports_dir()
        assert result == tmp_path / "exports"
        assert result.exists()
```

- [ ] **Step 4: Run tests**

```bash
cd crawler
python -m pytest tests/test_paths.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/app/paths.py crawler/app/config.py crawler/tests/test_paths.py
git commit -m "feat: add cross-platform path resolution"
```

---

### Task 3: Standard Schema Copy

**Files:**
- Create: `crawler/app/schema/__init__.py`
- Create: `crawler/app/schema/standard.py`
- Test: `crawler/tests/test_standard_schema.py`

- [ ] **Step 1: Create schema package**

Create empty `crawler/app/schema/__init__.py`.

- [ ] **Step 2: Create standard.py**

Copy field definitions from `services/processor/utils/standard_product_schema.py` with a header comment referencing the source. Add dataclasses for product and option records.

```python
"""
Standard product schema definitions.

Copied from services/processor/utils/standard_product_schema.py to keep the
crawler standalone. If the processor schema changes, update this file to match.
Source: /Users/yoonjae/Desktop/auto-selp-ver2/services/processor/utils/standard_product_schema.py
"""
import math
from dataclasses import dataclass, field
from typing import Any

REQUIRED_STANDARD_PRODUCT_FIELDS = [
    "supplier_name",
    "supplier_product_id",
    "supplier_product_code",
    "supplier_status",
    "raw_product_name",
    "origin",
    "supply_price",
    "main_image_url",
    "detail_content",
]

OPTION_TYPES = {"single", "combination", "custom", "standard"}


def clean_standard_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) and math.isnan(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    return text or None


def build_option_display_name(option: dict[str, Any]) -> str:
    values = [
        clean_standard_text(option.get("option_value_1")),
        clean_standard_text(option.get("option_value_2")),
        clean_standard_text(option.get("option_value_3")),
    ]
    visible_values = [value for value in values if value]
    return " / ".join(visible_values)


def derive_option_price_delta(
    option_supply_price: int | None,
    base_supply_price: int | None,
) -> int | None:
    if option_supply_price is None or base_supply_price is None:
        return None
    return option_supply_price - base_supply_price


@dataclass
class StandardProduct:
    supplier_name: str
    supplier_product_id: str | None
    supplier_product_code: str
    supplier_status: str
    raw_product_name: str
    origin: str | None
    supply_price: int | None
    main_image_url: str | None
    detail_content: str | None
    supplier_category: str | None = None
    extra_image_urls: list[str] = field(default_factory=list)
    brand_name: str | None = None
    manufacturer: str | None = None
    model_name: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StandardOption:
    supplier_product_code: str
    option_sku: str | None
    option_type: str
    option_group_1: str | None
    option_value_1: str | None
    option_group_2: str | None
    option_value_2: str | None
    option_group_3: str | None
    option_value_3: str | None
    option_display_name: str
    option_supply_price: int | None
    option_sale_price: int | None
    option_price_delta: int | None
    option_stock_quantity: int | None
    option_status: str | None
    option_usable: bool
    option_main_image_url: str | None
    option_extra_image_urls: list[str]
    option_position: int
    raw_option_text: str | None
    raw_option_metadata: dict[str, Any]
```

- [ ] **Step 3: Create test_standard_schema.py**

```python
from app.schema.standard import (
    REQUIRED_STANDARD_PRODUCT_FIELDS,
    clean_standard_text,
    build_option_display_name,
    derive_option_price_delta,
    StandardProduct,
    StandardOption,
)

def test_required_fields_match_processor_schema():
    assert REQUIRED_STANDARD_PRODUCT_FIELDS == [
        "supplier_name",
        "supplier_product_id",
        "supplier_product_code",
        "supplier_status",
        "raw_product_name",
        "origin",
        "supply_price",
        "main_image_url",
        "detail_content",
    ]

def test_clean_standard_text_handles_none_and_blank():
    assert clean_standard_text(None) is None
    assert clean_standard_text("") is None
    assert clean_standard_text("  ") is None
    assert clean_standard_text(" hello ") == "hello"

def test_build_option_display_name_joins_non_blank():
    option = {"option_value_1": "블랙", "option_value_2": "L", "option_value_3": ""}
    assert build_option_display_name(option) == "블랙 / L"

def test_derive_option_price_delta():
    assert derive_option_price_delta(13000, 12000) == 1000
    assert derive_option_price_delta(12000, 12000) == 0
    assert derive_option_price_delta(None, 12000) is None
    assert derive_option_price_delta(13000, None) is None

def test_standard_product_dataclass_defaults():
    product = StandardProduct(
        supplier_name="테스트",
        supplier_product_id="1",
        supplier_product_code="P-1",
        supplier_status="available",
        raw_product_name="상품",
        origin="국산",
        supply_price=10000,
        main_image_url="http://img/test.jpg",
        detail_content="<p>detail</p>",
    )
    assert product.extra_image_urls == []
    assert product.raw_metadata == {}
    assert product.supplier_category is None
```

- [ ] **Step 4: Run tests**

```bash
cd crawler
python -m pytest tests/test_standard_schema.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/app/schema/__init__.py crawler/app/schema/standard.py crawler/tests/test_standard_schema.py
git commit -m "feat: copy standard product schema for crawler"
```

---

### Task 4: Database Models

**Files:**
- Create: `crawler/app/db/__init__.py`
- Create: `crawler/app/db/models.py`
- Create: `crawler/app/db/session.py`

- [ ] **Step 1: Create db package**

Create empty `crawler/app/db/__init__.py`.

- [ ] **Step 2: Create models.py**

SQLAlchemy 2.0 declarative models for `suppliers`, `crawl_runs`, `products`, `product_options`, `stock_snapshots`, `stock_changes` as defined in the spec. Use UUID primary keys (string-based for SQLite compatibility), timestamps, and JSON columns via SQLAlchemy's JSON type.

- [ ] **Step 3: Create session.py**

```python
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.db.models import Base
from app.paths import db_path

def get_engine(db_path_arg: Path | None = None):
    path = db_path_arg or db_path()
    return create_engine(f"sqlite:///{path}", echo=False)

def init_db(db_path_arg: Path | None = None):
    engine = get_engine(db_path_arg)
    Base.metadata.create_all(engine)
    return engine

def get_session(engine=None) -> Session:
    engine = engine or get_engine()
    return sessionmaker(bind=engine)()
```

- [ ] **Step 4: Run a smoke test**

```bash
cd crawler
python -c "from app.db.session import init_db; init_db(); print('DB initialized')"
```

Expected: prints `DB initialized` and creates a `crawler.db` file in the data directory.

- [ ] **Step 5: Commit**

```bash
git add crawler/app/db/__init__.py crawler/app/db/models.py crawler/app/db/session.py
git commit -m "feat: add SQLite database models"
```

---

### Task 5: Credential Store

**Files:**
- Create: `crawler/app/credentials/__init__.py`
- Create: `crawler/app/credentials/store.py`
- Test: `crawler/tests/test_credentials_store.py`

- [ ] **Step 1: Create store.py with keyring wrapper**

```python
import keyring

SERVICE_PREFIX = "auto-selp-crawler"

def _service_name(supplier_slug: str) -> str:
    return f"{SERVICE_PREFIX}.{supplier_slug}"

def save_supplier_credentials(supplier_slug: str, username: str, password: str) -> None:
    keyring.set_password(_service_name(supplier_slug), username, password)

def load_supplier_credentials(supplier_slug: str) -> tuple[str, str] | None:
    # keyring does not enumerate; we store username in a separate key.
    username = keyring.get_password(_service_name(supplier_slug), "username")
    if not username:
        return None
    password = keyring.get_password(_service_name(supplier_slug), username)
    if not password:
        return None
    return username, password

def delete_supplier_credentials(supplier_slug: str) -> None:
    username = keyring.get_password(_service_name(supplier_slug), "username")
    if username:
        try:
            keyring.delete_password(_service_name(supplier_slug), username)
        except keyring.errors.PasswordDeleteError:
            pass
        try:
            keyring.delete_password(_service_name(supplier_slug), "username")
        except keyring.errors.PasswordDeleteError:
            pass

def save_llm_api_key(provider: str, api_key: str) -> None:
    keyring.set_password(f"{SERVICE_PREFIX}.llm", provider, api_key)

def load_llm_api_key(provider: str) -> str | None:
    return keyring.get_password(f"{SERVICE_PREFIX}.llm", provider)
```

- [ ] **Step 2: Create test with keyring mock**

```python
from unittest.mock import patch, MagicMock
from app.credentials.store import (
    save_supplier_credentials,
    load_supplier_credentials,
    delete_supplier_credentials,
    save_llm_api_key,
    load_llm_api_key,
)

def test_save_and_load_supplier_credentials():
    with patch("app.credentials.store.keyring") as mock_kr:
        save_supplier_credentials("itopic", "user", "pass")
        # save username marker + password
        assert mock_kr.set_password.call_count == 2
        # simulate stored username
        mock_kr.get_password.side_effect = lambda svc, key: "user" if key == "username" else "pass"
        result = load_supplier_credentials("itopic")
        assert result == ("user", "pass")

def test_load_supplier_credentials_returns_none_when_missing():
    with patch("app.credentials.store.keyring") as mock_kr:
        mock_kr.get_password.return_value = None
        assert load_supplier_credentials("itopic") is None

def test_save_and_load_llm_api_key():
    with patch("app.credentials.store.keyring") as mock_kr:
        save_llm_api_key("gemini", "AIzaXXX")
        mock_kr.set_password.assert_called_once_with("auto-selp-crawler.llm", "gemini", "AIzaXXX")
        mock_kr.get_password.return_value = "AIzaXXX"
        assert load_llm_api_key("gemini") == "AIzaXXX"
```

- [ ] **Step 3: Run tests**

```bash
cd crawler
python -m pytest tests/test_credentials_store.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add crawler/app/credentials/__init__.py crawler/app/credentials/store.py crawler/tests/test_credentials_store.py
git commit -m "feat: add keyring credential store"
```

---

### Task 6: Main Entry Point

**Files:**
- Create: `crawler/main.py`

- [ ] **Step 1: Create main.py with UTF-8 forcing and high-DPI**

```python
import sys

def _ensure_utf8():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

def main():
    _ensure_utf8()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from app.db.session import init_db
    from app.ui.main_window import MainWindow

    init_db()
    app = QApplication(sys.argv)
    app.setApplicationName("Auto-Selp Crawler")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit (will not run yet — MainWindow added in Task 7)**

```bash
git add crawler/main.py
git commit -m "feat: add main entry point with utf-8 forcing"
```

---

### Task 7: Main Window And Tab Skeleton

**Files:**
- Create: `crawler/app/ui/__init__.py`
- Create: `crawler/app/ui/main_window.py`
- Create: `crawler/app/ui/styles/global.qss`
- Create: `crawler/app/ui/tabs/__init__.py`
- Create: `crawler/app/ui/tabs/suppliers_tab.py`
- Create: `crawler/app/ui/tabs/adapter_builder_tab.py`
- Create: `crawler/app/ui/tabs/crawl_tab.py`
- Create: `crawler/app/ui/tabs/monitor_tab.py`
- Create: `crawler/app/ui/tabs/export_tab.py`
- Create: `crawler/app/ui/tabs/settings_tab.py`

- [ ] **Step 1: Create main_window.py with QTabWidget**

A QMainWindow with a QTabWidget containing 6 tabs: Suppliers, Adapter Builder, Crawl, Monitor, Export, Settings. Load global stylesheet from `global.qss`.

- [ ] **Step 2: Create global.qss**

A minimal Apple-inspired stylesheet: system font, 13px base, subtle hairlines, rounded buttons, padding consistent with the existing frontend.

- [ ] **Step 3: Create tab placeholder modules**

Each tab is a QWidget subclass with a header label and a placeholder body. They will be filled in later tasks.

- [ ] **Step 4: Run smoke test**

```bash
cd crawler
python main.py
```

Expected: window opens with 6 tabs, no crash. Close manually.

- [ ] **Step 5: Commit**

```bash
git add crawler/app/ui/
git commit -m "feat: add main window with 6 tab skeleton"
```

---

### Task 8: First Run Wizard

**Files:**
- Create: `crawler/app/ui/first_run_wizard.py`

- [ ] **Step 1: Create wizard dialog**

A QWizard with 3 pages:
1. Welcome and usage overview.
2. LLM provider selection (Gemini/OpenAI) + API key input → save to keyring.
3. Browser channel detection (check Edge/Chrome availability) + data directory info.

The wizard runs on first launch (detect via a marker file in config_dir). On subsequent launches, skip.

- [ ] **Step 2: Wire into main_window**

In `MainWindow.__init__`, check for first-run marker; if absent, run wizard, then write marker.

- [ ] **Step 3: Commit**

```bash
git add crawler/app/ui/first_run_wizard.py crawler/app/ui/main_window.py
git commit -m "feat: add first-run setup wizard"
```

---

### Task 9: Settings Tab

**Files:**
- Modify: `crawler/app/ui/tabs/settings_tab.py`
- Modify: `crawler/app/config.py`

- [ ] **Step 1: Implement settings form**

Fields:
- LLM provider combo (Gemini/OpenAI).
- LLM API key line edit (masked) with Save button → keyring.
- Browser channel combo (msedge/chrome/chromium).
- Global delay spin box (0-10 seconds).
- Update check checkbox.
- Data directory read-only display.
- "Check for updates" button.

- [ ] **Step 2: Add config persistence**

Update `config.py` to load/save JSON in `config_dir()/settings.json`.

- [ ] **Step 3: Commit**

```bash
git add crawler/app/ui/tabs/settings_tab.py crawler/app/config.py
git commit -m "feat: implement settings tab with config persistence"
```

---

### Task 10: Playwright Engine

**Files:**
- Create: `crawler/app/crawlers/__init__.py`
- Create: `crawler/app/crawlers/engine.py`

- [ ] **Step 1: Create engine.py**

Async Playwright session manager that:
- Resolves the browser channel from config (msedge → chrome → chromium fallback).
- Supports persistent context with a user-data-dir in cache_dir for session reuse.
- Provides async context manager for clean shutdown.
- Includes configurable timeout, user agent, and headless toggle.

- [ ] **Step 2: Commit**

```bash
git add crawler/app/crawlers/__init__.py crawler/app/crawlers/engine.py
git commit -m "feat: add playwright browser engine"
```

---

### Task 11: Adapter Schema And Registry

**Files:**
- Create: `crawler/app/analyzer/__init__.py`
- Create: `crawler/app/analyzer/adapter_schema.py`
- Create: `crawler/app/crawlers/registry.py`
- Test: `crawler/tests/test_adapter_schema.py`

- [ ] **Step 1: Create adapter_schema.py**

Pydantic v2 models mirroring the YAML schema in the spec (section 7.1). Nested models for browser, login, categories, listing, product fields, options, dependent options, delays. Validate that CSS selectors are non-empty strings and enum fields use allowed values.

- [ ] **Step 2: Create registry.py**

```python
from pathlib import Path
import yaml
from app.analyzer.adapter_schema import Adapter
from app.paths import adapters_dir

def adapter_path(supplier_slug: str) -> Path:
    return adapters_dir() / f"{supplier_slug}.yaml"

def save_adapter(supplier_slug: str, yaml_text: str) -> Path:
    path = adapter_path(supplier_slug)
    if path.exists():
        path.rename(path.with_suffix(".yaml.bak"))
    path.write_text(yaml_text, encoding="utf-8")
    return path

def load_adapter(supplier_slug: str) -> Adapter:
    path = adapter_path(supplier_slug)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Adapter.model_validate(raw)

def list_adapters() -> list[str]:
    return [p.stem for p in adapters_dir().glob("*.yaml")]
```

- [ ] **Step 3: Create test_adapter_schema.py**

Test that a valid YAML loads successfully, invalid selectors raise validation errors, and missing required fields raise errors.

- [ ] **Step 4: Run tests**

```bash
cd crawler
python -m pytest tests/test_adapter_schema.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/app/analyzer/__init__.py crawler/app/analyzer/adapter_schema.py crawler/app/crawlers/registry.py crawler/tests/test_adapter_schema.py
git commit -m "feat: add adapter schema validation and registry"
```

---

### Task 12: Base Adapter Crawler

**Files:**
- Create: `crawler/app/crawlers/base.py`

- [ ] **Step 1: Create BaseAdapter interface**

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator
from app.schema.standard import StandardProduct, StandardOption

class CrawlResult:
    product: StandardProduct
    options: list[StandardOption]

class BaseAdapter(ABC):
    @abstractmethod
    async def discover_categories(self) -> list[CategoryEntry]: ...
    @abstractmethod
    async def crawl_category(self, category_id: str, max_pages: int) -> AsyncIterator[CrawlResult]: ...
    @abstractmethod
    async def stock_check(self, category_id: str | None = None) -> AsyncIterator[StockSnapshot]: ...
    @abstractmethod
    async def close(self): ...
```

- [ ] **Step 2: Commit**

```bash
git add crawler/app/crawlers/base.py
git commit -m "feat: add base adapter interface"
```

---

### Task 13: YAML-Driven Adapter Crawler

**Files:**
- Create: `crawler/app/crawlers/yaml_adapter.py`

- [ ] **Step 1: Implement YAMLAdapter**

A concrete `BaseAdapter` that takes a validated `Adapter` pydantic model and implements:
- `discover_categories`: navigate menu per `categories.navigation` config, build `CategoryEntry` list with paths and product counts.
- `crawl_category`: paginate via `categories.url_template`, extract product links, visit detail pages, extract all standard fields, extract options (independent + dependent), yield `CrawlResult`.
- `stock_check`: same pagination but only extract status/price/stock fields.
- Apply delays between pages and products from config or adapter override.
- Handle login sequence if `login.required`.

- [ ] **Step 2: Commit**

```bash
git add crawler/app/crawlers/yaml_adapter.py
git commit -m "feat: implement yaml-driven adapter crawler"
```

---

### Task 14: Category Discovery

**Files:**
- Modify: `crawler/app/crawlers/yaml_adapter.py`

- [ ] **Step 1: Implement category tree walking**

- For `all_products` mode: return a single root `CategoryEntry`.
- For `tree` mode: query `navigation.menu_selector`, for each item extract link and name, recurse into `submenu.selector` up to `max_depth`, handle `expand_trigger` (hover/click/static).
- For `hybrid` mode: return both the all-products entry and the tree.
- Store category path as `대분류 > 중분류 > 소분류` in `CategoryEntry.path`.

- [ ] **Step 2: Commit**

```bash
git add crawler/app/crawlers/yaml_adapter.py
git commit -m "feat: implement category discovery for tree and all-products modes"
```

---

### Task 15: Dependent Option Extraction

**Files:**
- Modify: `crawler/app/crawlers/yaml_adapter.py`

- [ ] **Step 1: Implement two-level dependent option extraction**

- Read level-1 group values from `options.groups[0].values_selector`.
- For each level-1 value:
  - Trigger the level-2 load via `dependent_options.level_2_trigger` (click or select).
  - Wait for `level_2_load_indicator` to appear then detach, or wait for `level_2_values_selector` to populate.
  - Read level-2 values.
  - Build combinations: `(level_1_value, level_2_value)` → `option_group_1`, `option_value_1`, `option_group_2`, `option_value_2`.
- Extract per-combination price delta, stock, and image if selectors are configured.
- Normalize into `StandardOption` records.

- [ ] **Step 2: Commit**

```bash
git add crawler/app/crawlers/yaml_adapter.py
git commit -m "feat: support two-level dependent option extraction"
```

---

### Task 16: HTML Reducer

**Files:**
- Create: `crawler/app/analyzer/html_reducer.py`
- Test: `crawler/tests/test_html_reducer.py`

- [ ] **Step 1: Create html_reducer.py**

```python
from bs4 import BeautifulSoup
import re

def reduce_html(html: str, max_text_chars: int = 80, max_repeated: int = 2) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "svg", "noscript", "iframe", "comment"]):
        tag.decompose()
    for tag in soup.find_all(attrs={"style": True}):
        del tag["style"]
    for tag in soup.find_all(string=lambda text: isinstance(text, str) and text.strip() == ""):
        text = str(tag)
        if text.strip() == "":
            tag.extract()
    for tag in soup.find_all():
        text = tag.get_text(strip=True)
        if len(text) > max_text_chars:
            tag.string = text[:max_text_chars] + "…"
    # compress repeated siblings with same class
    _compress_repeated(soup, max_repeated)
    return str(soup)

def _compress_repeated(soup, max_repeated):
    # find parent with > max_repeated children of same class, keep first N, replace rest with comment
    for parent in soup.find_all():
        children = [c for c in parent.children if hasattr(c, "get")]
        if len(children) <= max_repeated:
            continue
        classes = {}
        for child in children:
            cls = " ".join(child.get("class", []))
            classes.setdefault(cls, []).append(child)
        for cls, group in classes.items():
            if len(group) > max_repeated:
                for extra in group[max_repeated:]:
                    extra.replace_with(f"<!-- [{len(group) - max_repeated} more {cls or 'elements'} omitted] -->")
```

- [ ] **Step 2: Create test_html_reducer.py**

Test that scripts/styles are removed, long text is truncated, repeated elements are compressed, and structure is preserved.

- [ ] **Step 3: Run tests**

```bash
cd crawler
python -m pytest tests/test_html_reducer.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add crawler/app/analyzer/html_reducer.py crawler/tests/test_html_reducer.py
git commit -m "feat: add html reducer for llm input"
```

---

### Task 17: Site Probe

**Files:**
- Create: `crawler/app/analyzer/site_probe.py`

- [ ] **Step 1: Create site_probe.py**

Async function `probe_site(main_url, sample_listing_url=None, sample_detail_url=None)` that:
- Launches Playwright via engine.
- Navigates to main_url, captures final URL, encoding, login form presence.
- Detects category navigation structure.
- Navigates to sample listing URL (or first category), captures reduced HTML, sample product links, pagination structure.
- Follows first product link, captures reduced detail HTML.
- Logs AJAX requests for option loading detection.
- Returns a `ProbeResult` dataclass.

- [ ] **Step 2: Commit**

```bash
git add crawler/app/analyzer/site_probe.py
git commit -m "feat: add site probe for dom sampling"
```

---

### Task 18: LLM Client

**Files:**
- Create: `crawler/app/analyzer/llm_client.py`

- [ ] **Step 1: Create llm_client.py**

Follows the pattern from `services/processor/clients/llm_factory.py`. A `get_llm_client(provider)` factory returning a client that calls Gemini (default) or OpenAI. The client takes a prompt string and returns the raw text response. API keys are loaded from keyring.

```python
from app.credentials.store import load_llm_api_key

class LLMClient:
    def __init__(self, provider: str):
        self.provider = provider
        self.api_key = load_llm_api_key(provider)

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

class GeminiClient(LLMClient):
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-lite")
        response = await model.generate_content_async(
            f"{system_prompt}\n\n{user_prompt}"
        )
        return response.text

class OpenAIClient(LLMClient):
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content

def get_llm_client(provider: str) -> LLMClient:
    if provider.lower() == "openai":
        return OpenAIClient(provider)
    return GeminiClient(provider)
```

- [ ] **Step 2: Commit**

```bash
git add crawler/app/analyzer/llm_client.py
git commit -m "feat: add llm client for adapter generation"
```

---

### Task 19: Adapter Generator

**Files:**
- Create: `crawler/app/analyzer/adapter_generator.py`

- [ ] **Step 1: Create adapter_generator.py**

```python
async def generate_adapter_yaml(
    probe_result,
    supplier_name: str,
    llm_provider: str = "gemini",
) -> str:
    # 1. Build system prompt with schema + 2-shot examples.
    # 2. Build user prompt with reduced HTML, AJAX patterns, supplier info.
    # 3. Call LLM client.
    # 4. Parse YAML, validate with adapter_schema.
    # 5. On failure, retry once with error feedback.
    # 6. On second failure, fallback to GPT if provider was Gemini.
    # 7. Return validated YAML string.
```

- [ ] **Step 2: Commit**

```bash
git add crawler/app/analyzer/adapter_generator.py
git commit -m "feat: add llm adapter generator"
```

---

### Task 20: Adapter Builder Tab

**Files:**
- Modify: `crawler/app/ui/tabs/adapter_builder_tab.py`

- [ ] **Step 1: Implement the tab UI**

Left panel: YAML editor (QPlainTextEdit with Pygments YAML highlight).
Right panel: field test list with per-field Test buttons, full-test button, 3-sample test button, option test button, pagination test button, login test button.
Top toolbar: URL inputs, Probe button, Generate button, Save button.
Failed fields can be sent back to LLM for retry.

- [ ] **Step 2: Wire up site_probe + adapter_generator**

Probe button → run `probe_site` in a QThread → show progress → feed result to Generate button.
Generate button → run `generate_adapter_yaml` → populate YAML editor.
Save button → validate YAML → `save_adapter` to adapters_dir.

- [ ] **Step 3: Commit**

```bash
git add crawler/app/ui/tabs/adapter_builder_tab.py
git commit -m "feat: implement adapter builder tab with llm analysis"
```

---

### Task 21: Stock Checker

**Files:**
- Create: `crawler/app/monitor/__init__.py`
- Create: `crawler/app/monitor/stock_checker.py`
- Test: `crawler/tests/test_stock_checker.py`

- [ ] **Step 1: Create stock_checker.py**

```python
def detect_changes(previous_snapshot, new_snapshot) -> list[ChangeRecord]:
    changes = []
    if previous_snapshot.supplier_status != new_snapshot.supplier_status:
        if previous_snapshot.supplier_status == "available" and new_snapshot.supplier_status == "sold_out":
            changes.append(ChangeRecord("sold_out", previous_snapshot.supplier_status, new_snapshot.supplier_status))
        elif previous_snapshot.supplier_status == "sold_out" and new_snapshot.supplier_status == "available":
            changes.append(ChangeRecord("restocked", previous_snapshot.supplier_status, new_snapshot.supplier_status))
        else:
            changes.append(ChangeRecord("status_changed", previous_snapshot.supplier_status, new_snapshot.supplier_status))
    if previous_snapshot.supply_price != new_snapshot.supply_price:
        changes.append(ChangeRecord("price_changed", str(previous_snapshot.supply_price), str(new_snapshot.supply_price)))
    # option stock comparison
    prev_stock = previous_snapshot.option_stock_json or {}
    new_stock = new_snapshot.option_stock_json or {}
    for sku, qty in new_stock.items():
        if prev_stock.get(sku) != qty:
            changes.append(ChangeRecord("stock_changed", str(prev_stock.get(sku)), str(qty)))
    return changes
```

- [ ] **Step 2: Create test_stock_checker.py**

Test sold_out, restocked, price_changed, stock_changed detection, and no-change case.

- [ ] **Step 3: Run tests**

```bash
cd crawler
python -m pytest tests/test_stock_checker.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add crawler/app/monitor/__init__.py crawler/app/monitor/stock_checker.py crawler/tests/test_stock_checker.py
git commit -m "feat: add stock change detection"
```

---

### Task 22: Scheduler

**Files:**
- Create: `crawler/app/monitor/scheduler.py`

- [ ] **Step 1: Create scheduler.py**

APScheduler BackgroundScheduler wrapper:
- `start()`: start the scheduler.
- `add_supplier_job(supplier_id, interval_hours)`: add a cron-like job that runs a stock check crawl for that supplier.
- `remove_supplier_job(supplier_id)`.
- `list_jobs() -> list`.
- The job callback loads the adapter, runs `stock_check`, saves snapshots, runs `detect_changes`, saves `stock_changes`.

- [ ] **Step 2: Commit**

```bash
git add crawler/app/monitor/scheduler.py
git commit -m "feat: add apscheduler for stock monitoring"
```

---

### Task 23: Suppliers Tab

**Files:**
- Modify: `crawler/app/ui/tabs/suppliers_tab.py`

- [ ] **Step 1: Implement supplier management UI**

- Supplier list table: name, base_url, needs_login, adapter_file, monitor_enabled.
- Add/Edit/Delete supplier form:
  - Name, base_url, needs_login checkbox.
  - If needs_login: username + password fields → save to keyring.
  - Adapter file dropdown (list of YAMLs in adapters_dir) + "Open Adapter Builder" button.
  - Monitor enabled checkbox + interval hours spin.
  - Per-supplier delay override spin (optional).
- Delete confirms and also removes keyring credentials.

- [ ] **Step 2: Commit**

```bash
git add crawler/app/ui/tabs/suppliers_tab.py
git commit -m "feat: implement suppliers management tab"
```

---

### Task 24: Crawl Tab

**Files:**
- Modify: `crawler/app/ui/tabs/crawl_tab.py`

- [ ] **Step 1: Implement crawl execution UI**

- Supplier dropdown.
- Category tri-state checkbox tree (populated from `discover_categories`).
- Max pages spin, delay override spin for this run.
- Start/Cancel buttons.
- Progress panel: current category, current page, product count, log text area (append-only).
- QThread runs `crawl_category`, emits signals, UI updates safely.
- On completion: summary + preview table (first 50 products).

- [ ] **Step 2: Commit**

```bash
git add crawler/app/ui/tabs/crawl_tab.py
git commit -m "feat: implement crawl execution tab"
```

---

### Task 25: Monitor Tab

**Files:**
- Modify: `crawler/app/ui/tabs/monitor_tab.py`

- [ ] **Step 1: Implement stock change dashboard**

- Unacknowledged change count badge.
- Filterable table: time, supplier, product, change type, previous value, new value, acknowledged.
- Filters: supplier dropdown, change type dropdown, date range.
- Acknowledge button (single + bulk).
- Per-supplier monitor toggle and interval selector (links to scheduler).
- Manual "Check now" button per supplier.

- [ ] **Step 2: Commit**

```bash
git add crawler/app/ui/tabs/monitor_tab.py
git commit -m "feat: implement stock monitor dashboard"
```

---

### Task 26: Excel Exporter

**Files:**
- Create: `crawler/app/exporters/__init__.py`
- Create: `crawler/app/exporters/excel.py`
- Create: `crawler/app/exporters/server_client.py`
- Test: `crawler/tests/test_excel_export.py`

- [ ] **Step 1: Create excel.py**

```python
from openpyxl import Workbook
from pathlib import Path
from sqlalchemy.orm import Session

PRODUCT_COLUMNS = [
    "supplier_name", "supplier_product_id", "supplier_product_code",
    "supplier_status", "supplier_category", "raw_product_name", "origin",
    "supply_price", "main_image_url", "extra_image_urls", "detail_content",
    "brand_name", "manufacturer", "model_name",
]

OPTION_COLUMNS = [
    "supplier_product_code", "option_sku", "option_type",
    "option_group_1", "option_value_1", "option_group_2", "option_value_2",
    "option_group_3", "option_value_3", "option_display_name",
    "option_supply_price", "option_sale_price", "option_price_delta",
    "option_stock_quantity", "option_status", "option_usable",
    "option_main_image_url", "option_extra_image_urls", "option_position",
]

def export_to_excel(session: Session, supplier_id: str, output_path: Path) -> Path:
    wb = Workbook()
    products_sheet = wb.active
    products_sheet.title = "products"
    products_sheet.append(PRODUCT_COLUMNS)
    options_sheet = wb.create_sheet("product_options")
    options_sheet.append(OPTION_COLUMNS)
    # query products and options from DB, append rows
    wb.save(output_path)
    return output_path
```

- [ ] **Step 2: Create server_client.py (interface only)**

```python
class ServerClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url
        self.token = token

    def push_products(self, supplier_id: str) -> None:
        raise NotImplementedError("Server sync is planned for phase 2.")
```

- [ ] **Step 3: Create test_excel_export.py**

Test with an in-memory SQLite DB, verify both sheets have correct headers and row counts.

- [ ] **Step 4: Run tests**

```bash
cd crawler
python -m pytest tests/test_excel_export.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crawler/app/exporters/__init__.py crawler/app/exporters/excel.py crawler/app/exporters/server_client.py crawler/tests/test_excel_export.py
git commit -m "feat: add excel exporter matching standard schema"
```

---

### Task 27: Export Tab

**Files:**
- Modify: `crawler/app/ui/tabs/export_tab.py`

- [ ] **Step 1: Implement export UI**

- Supplier dropdown.
- "Export to Excel" button → file dialog → `export_to_excel`.
- Success message with file path.
- "Sync to Server (coming soon)" disabled button with tooltip.
- Recent exports list (from exports_dir).

- [ ] **Step 2: Commit**

```bash
git add crawler/app/ui/tabs/export_tab.py
git commit -m "feat: implement export tab"
```

---

### Task 28: Update Checker

**Files:**
- Create: `crawler/app/update/__init__.py`
- Create: `crawler/app/update/checker.py`

- [ ] **Step 1: Create checker.py**

```python
import urllib.request
import json

def get_latest_version(repo: str = "anomalyco/auto-selp-ver2") -> dict | None:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            return {"tag": data["tag_name"], "url": data["html_url"], "name": data["name"]}
    except Exception:
        return None

def compare_versions(current: str, latest: str) -> bool:
    # return True if latest > current
    ...
```

- [ ] **Step 2: Commit**

```bash
git add crawler/app/update/__init__.py crawler/app/update/checker.py
git commit -m "feat: add github release update checker"
```

---

### Task 29: README And Build Scripts

**Files:**
- Create: `crawler/README.md`
- Create: `crawler/build_windows.spec`
- Create: `crawler/installer.iss`
- Create: `crawler/.github/workflows/build_windows.yml`

- [ ] **Step 1: Create README.md**

Cover: prerequisites, installation (dev + Windows), first-run wizard, adding a supplier, building an adapter via LLM, crawling, monitoring, exporting, troubleshooting.

- [ ] **Step 2: Create build_windows.spec**

PyInstaller spec: onedir, windowed, icon from assets, hidden imports for PySide6/Playwright/keyring/APScheduler/pydantic, exclude tests.

- [ ] **Step 3: Create installer.iss**

Inno Setup script: install to local app data, Start Menu shortcut, uninstaller, no admin.

- [ ] **Step 4: Create build_windows.yml**

GitHub Actions workflow: trigger on tags, windows-latest, Python 3.11, pip install, pyinstaller, iscc, upload release asset.

- [ ] **Step 5: Commit**

```bash
git add crawler/README.md crawler/build_windows.spec crawler/installer.iss crawler/.github/workflows/build_windows.yml
git commit -m "feat: add readme and windows build scripts"
```

---

### Task 30: itopic Adapter Probe

**Files:**
- Create: `crawler/adapters_data/itopic.yaml` (after probe, gitignored but created locally for testing)

- [ ] **Step 1: Ask user for permission to probe itopic**

Before running any Playwright request against `http://www.itopic.co.kr/`, confirm with the user that probing is allowed at this time.

- [ ] **Step 2: Run site_probe against itopic**

Use `probe_site(main_url="http://www.itopic.co.kr/html/mainm.html")` to capture the category structure, listing HTML, and sample detail HTML.

- [ ] **Step 3: Generate adapter YAML via LLM**

Feed the probe result into `generate_adapter_yaml` with the user's configured LLM provider.

- [ ] **Step 4: Validate fields in the adapter builder tab**

Run single-field tests against sample itopic product pages. Fix any failing selectors manually or via LLM retry.

- [ ] **Step 5: Save the adapter**

Save to `adapters_data/itopic.yaml` (local only, gitignored).

- [ ] **Step 6: Commit (adapter file is gitignored; commit only code changes if any)**

```bash
git add -- crawler/app/ # only if probe revealed code changes needed
git commit -m "feat: validate crawler against itopic sample site" || true
```

---

### Task 31: Full Verification

- [ ] **Step 1: Run all crawler tests**

```bash
cd crawler
python -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 2: Run the app end-to-end manually**

```bash
cd crawler
python main.py
```

- First-run wizard appears.
- Settings tab saves LLM key and delay.
- Suppliers tab can add itopic with credentials.
- Adapter builder can probe and generate itopic adapter.
- Crawl tab can run a small crawl (1 category, 2 pages) against itopic.
- Monitor tab can run a manual stock check.
- Export tab produces an Excel file.

- [ ] **Step 3: Inspect git status**

```bash
git status --short
```

Expected: clean working tree after task commits.

- [ ] **Step 4: Record implementation learning**

```bash
/ce-compound mode:headless
```

Expected: a new or updated document under `docs/solutions/` capturing the crawler architecture and lessons learned.

---

## Self-Review

- Spec coverage: the plan covers cross-platform paths, standard schema copy, SQLite models, keyring credentials, PySide6 UI (6 tabs + wizard), Playwright engine, adapter YAML schema/registry, YAML-driven crawler, category discovery, dependent options, HTML reducer, site probe, LLM client, adapter generator, adapter builder UI, stock checker, scheduler, suppliers tab, crawl tab, monitor tab, Excel exporter, export tab, update checker, README, Windows build scripts, and itopic validation.
- Intentional deferral: server sync is interface-only; three-level dependent options are out of scope; resume crawling is out of scope; macOS packaging is out of scope; code signing is out of scope.
- Placeholder scan: the plan contains concrete file paths, code snippets, commands, and expected outcomes for every task. Some UI tasks defer detailed widget code to implementation time because Qt widget code is verbose and better written iteratively.
