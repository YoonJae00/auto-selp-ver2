from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Product, ProductOption


# 서버(services/processor)의 도매 상품대장 인제스트 형식에 맞춘 헤더.
# 단일 시트 · 한글 헤더 · 옵션은 인라인(옵션값/가격 CSV). 서버는 헤더명으로 매칭하며
# FIELD_FALLBACKS의 대표 헤더를 그대로 쓰면 column_mapping 없이 업로드된다.
# 원본: services/processor/utils/wholesale_upload.py (FIELD_FALLBACKS)
WHOLESALE_COLUMNS = [
    "상태",          # wholesale_status (required)
    "제품번호",       # wholesale_product_id (required)
    "상품코드",       # product_code (required, upsert key)
    "상품명",         # original_name (required)
    "가격",          # price_wholesale_raw (required) — 옵션 있으면 옵션가격 CSV
    "원산지",         # origin (required)
    "목록이미지1",     # image_list_1 (required)
    "상세이미지",      # image_detail (required)
    "옵션값",         # option_values_raw (옵션명 CSV, 가격과 1:1 정렬)
    "옵션이미지",      # option_image_urls_raw (옵션별 이미지 CSV)
    "목록이미지2",     # image_list_2
    "목록이미지3",     # image_list_3
    "목록이미지4",     # image_list_4
    "목록이미지5",     # image_list_5
    "등록일",         # wholesale_registered_at
]

# 서버 option_usable = 상태 not in {품절, 판매중지, 중지}. 크롤러의 정규화 상태를
# 서버가 이해하는 한글 상태로 변환한다.
_STATUS_KO = {
    "sold_out": "품절",
    "stopped": "판매중지",
    "available": "판매중",
}


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


def _status_ko(status: str | None) -> str:
    if not status:
        return "판매중"  # 상태 불명은 판매 가능으로 (required 필드라 공란 회피)
    return _STATUS_KO.get(status, status)


def _at(values: list | None, index: int) -> str:
    if not values or index >= len(values):
        return ""
    return _text(values[index])


def _options_csv(options: list[ProductOption]) -> tuple[str, str, str]:
    """옵션명 / 옵션가격 / 옵션이미지를 1:1 정렬된 CSV로. 이름이 없는 옵션은 건너뛴다
    (서버는 옵션명 개수와 가격 개수가 다르면 옵션을 통째로 버린다)."""
    names: list[str] = []
    prices: list[str] = []
    images: list[str] = []
    for opt in options:
        name = opt.option_display_name or opt.option_value_1 or ""
        if not name:
            continue
        names.append(str(name))
        prices.append("" if opt.option_supply_price is None else str(opt.option_supply_price))
        images.append(opt.option_main_image_url or "")
    return ",".join(names), ",".join(prices), ",".join(images)


def export_to_excel(
    session: Session,
    supplier_id: str | None,
    output_path: Path,
) -> Path:
    wb = Workbook()
    sheet = wb.active
    sheet.title = "상품대장"
    sheet.append(WHOLESALE_COLUMNS)

    query = select(Product)
    if supplier_id:
        query = query.where(Product.supplier_id == supplier_id)
    query = query.order_by(Product.supplier_product_code)

    for product in session.execute(query).scalars().all():
        options = session.execute(
            select(ProductOption)
            .where(ProductOption.product_id == product.id)
            .order_by(ProductOption.option_position)
        ).scalars().all()
        opt_names, opt_prices, opt_images = _options_csv(options)

        # 가격: 옵션이 있으면 옵션별 가격 CSV(옵션값과 정렬), 없으면 단일 공급가.
        price_cell = opt_prices if (opt_names and opt_prices) else _text(product.supply_price)
        extras = product.extra_image_urls or []
        registered = product.first_seen_at.date().isoformat() if product.first_seen_at else ""

        sheet.append([
            _status_ko(product.supplier_status),
            _text(product.supplier_product_id),
            _text(product.supplier_product_code),
            _text(product.raw_product_name),
            price_cell,
            _text(product.origin),
            _text(product.main_image_url),
            _text(product.detail_content),
            opt_names,
            opt_images,
            _at(extras, 0),
            _at(extras, 1),
            _at(extras, 2),
            _at(extras, 3),
            registered,
        ])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path
