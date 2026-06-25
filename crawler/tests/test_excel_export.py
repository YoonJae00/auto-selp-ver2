from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Product, ProductOption, Supplier
from app.db.session import get_session
from app.exporters.excel import OPTION_COLUMNS, PRODUCT_COLUMNS, export_to_excel


def _setup_db(tmp_path: Path) -> Session:
    db_file = tmp_path / "test_export.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    return session


def _add_test_data(session: Session) -> tuple[str, str]:
    supplier = Supplier(name="테스트도매처", base_url="https://test.com")
    session.add(supplier)
    session.flush()

    product = Product(
        supplier_id=supplier.id,
        supplier_name="테스트도매처",
        supplier_product_code="P-001",
        supplier_product_id="1",
        supplier_status="available",
        raw_product_name="테스트 상품",
        origin="국산",
        supply_price=12000,
        main_image_url="https://img/test.jpg",
        detail_content="<p>상세</p>",
        extra_image_urls=["https://img/2.jpg", "https://img/3.jpg"],
    )
    session.add(product)
    session.flush()

    opt1 = ProductOption(
        product_id=product.id,
        option_sku="P-001-1",
        option_type="combination",
        option_group_1="색상",
        option_value_1="블랙",
        option_display_name="블랙",
        option_supply_price=12000,
        option_price_delta=0,
        option_usable=True,
        option_position=1,
    )
    opt2 = ProductOption(
        product_id=product.id,
        option_sku="P-001-2",
        option_type="combination",
        option_group_1="색상",
        option_value_1="화이트",
        option_display_name="화이트",
        option_supply_price=13000,
        option_price_delta=1000,
        option_usable=True,
        option_position=2,
    )
    session.add(opt1)
    session.add(opt2)
    session.commit()

    return supplier.id, product.supplier_product_code


def test_export_creates_two_sheets(tmp_path: Path) -> None:
    session = _setup_db(tmp_path)
    supplier_id, _ = _add_test_data(session)

    output = tmp_path / "export.xlsx"
    result = export_to_excel(session, supplier_id, output)

    assert result == output
    assert output.exists()

    from openpyxl import load_workbook

    wb = load_workbook(output)
    assert "products" in wb.sheetnames
    assert "product_options" in wb.sheetnames


def test_products_sheet_has_correct_headers(tmp_path: Path) -> None:
    session = _setup_db(tmp_path)
    supplier_id, _ = _add_test_data(session)
    output = tmp_path / "export.xlsx"
    export_to_excel(session, supplier_id, output)

    from openpyxl import load_workbook

    wb = load_workbook(output)
    ws = wb["products"]
    headers = [cell.value for cell in ws[1]]
    assert headers == PRODUCT_COLUMNS


def test_options_sheet_has_correct_headers(tmp_path: Path) -> None:
    session = _setup_db(tmp_path)
    supplier_id, _ = _add_test_data(session)
    output = tmp_path / "export.xlsx"
    export_to_excel(session, supplier_id, output)

    from openpyxl import load_workbook

    wb = load_workbook(output)
    ws = wb["product_options"]
    headers = [cell.value for cell in ws[1]]
    assert headers == OPTION_COLUMNS


def test_products_and_options_row_counts(tmp_path: Path) -> None:
    session = _setup_db(tmp_path)
    supplier_id, _ = _add_test_data(session)
    output = tmp_path / "export.xlsx"
    export_to_excel(session, supplier_id, output)

    from openpyxl import load_workbook

    wb = load_workbook(output)
    products_ws = wb["products"]
    options_ws = wb["product_options"]

    product_rows = products_ws.max_row - 1
    option_rows = options_ws.max_row - 1

    assert product_rows == 1
    assert option_rows == 2


def test_export_with_no_supplier_id_exports_all(tmp_path: Path) -> None:
    session = _setup_db(tmp_path)
    _add_test_data(session)
    output = tmp_path / "export_all.xlsx"
    export_to_excel(session, None, output)

    from openpyxl import load_workbook

    wb = load_workbook(output)
    products_ws = wb["products"]
    assert products_ws.max_row - 1 == 1
