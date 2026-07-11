from __future__ import annotations

"""한국 쇼핑몰 솔루션(플랫폼) 감지 + 플랫폼별 프롬프트 힌트.

감지는 HTML/URL 안의 솔루션 고유 마커를 대소문자 무시 부분 문자열로 찾는다.
힌트는 어디까지나 '통상적인' DOM 구조 참고용이며, 실제 DOM에서 확인된
선택자만 사용해야 한다(각 힌트 문구에 명시).
"""


# 플랫폼별 마커. 하나라도 걸리면 해당 플랫폼으로 판정.
# 위에서부터 순서대로 검사하므로 더 구체적인 마커를 가진 것을 앞에 둔다.
_PLATFORM_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("cafe24", ("xans-", "/product/detail.html", "ec-base-")),
    ("makeshop", ("mk_menu", "shopdetail.html", "shopbrand.html")),
    ("godomall", ("/goods/goods_view.php", "godomall", "godo.co.kr")),
    ("youngcart", ("/shop/item.php", "g5_", "sit_title")),
    ("wisa", ("wisa", "/shop/goods/goods_view.php")),
]


def detect_platform(html: str, url: str) -> str | None:
    """HTML 본문과 URL에서 쇼핑몰 솔루션을 감지. 못 찾으면 None."""
    haystack = f"{html or ''}\n{url or ''}".lower()
    for name, markers in _PLATFORM_MARKERS:
        if any(marker in haystack for marker in markers):
            return name
    return None


_HINT_FOOTER = (
    "\n※ 이 힌트는 참고용이며, 실제 DOM에서 확인된 선택자만 사용하세요. "
    "힌트와 실제 DOM이 다르면 실제 DOM을 따르세요."
)

PLATFORM_PROMPT_HINTS: dict[str, str] = {
    "cafe24": (
        "카페24(cafe24) 표준 구조:\n"
        "- 상품명: .xans-product-detail 영역의 .name 또는 상세 상단 제목\n"
        "- 판매가/공급가: .xans-product-detail 내 가격 span (extract_number)\n"
        "- 상품코드: hidden input[name='product_no'] 또는 상품정보 테이블\n"
        "- 대표 이미지: .xans-product-image 안의 img (src/data-src)\n"
        "- 옵션: select[id^='product_option_id'] 또는 .xans-product-option select\n"
        "- 품절: 품절 이미지/영역이 .xans-product 영역 내에 노출됨\n"
        "- 목록 상품 링크: a[href*='/product/detail.html']"
    ),
    "makeshop": (
        "메이크샵(makeshop) 표준 구조:\n"
        "- 상품명: #form1 상단 상품명 영역, 보통 .prd_name 또는 상세 제목\n"
        "- 판매가/공급가: 가격 span/em (extract_number)\n"
        "- 상품코드/재고: hidden input[name='branduid'], 품절 판단은 input[name='maxq'] 값(0이면 품절)\n"
        "- 대표 이미지: #productDetail 또는 .prd_img 안의 img (src/data-src)\n"
        "- 옵션: select[name^='optionsno'] 또는 .selectOption select\n"
        "- 목록 상품 링크: a[href*='shopdetail.html'], 카테고리는 shopbrand.html"
    ),
    "godomall": (
        "고도몰(godomall) 표준 구조:\n"
        "- 상품명: .goods_view 영역의 상품명 제목\n"
        "- 판매가/공급가: #price 또는 가격 span (extract_number)\n"
        "- 상품코드: hidden input[name='goodsNo'] 또는 상품정보 테이블\n"
        "- 대표 이미지: .goods_image 또는 #objImg img (src/data-src)\n"
        "- 옵션: .opt_select select 또는 select[name^='optionSnoInput']\n"
        "- 목록 상품 링크: a[href*='goods_view.php']"
    ),
    "youngcart": (
        "영카트/그누보드(youngcart) 표준 구조:\n"
        "- 상품명: #sit_title 또는 .sit_title\n"
        "- 판매가/공급가: #sit_tot_price 내 가격 (extract_number)\n"
        "- 상품코드: hidden input[name='it_id'] (URL의 it_id 파라미터로도 추출 가능)\n"
        "- 대표 이미지: #sit_pvi 안의 img (src/data-src)\n"
        "- 옵션: #sit_opt select 또는 select[name^='io_type']\n"
        "- 목록 상품 링크: a[href*='item.php'] (it_id 파라미터 포함)"
    ),
    "wisa": (
        "위사(wisa) 표준 구조:\n"
        "- 상품명: 상세 상단 상품명 제목 영역\n"
        "- 판매가/공급가: 가격 span/em (extract_number)\n"
        "- 상품코드: goodsNo/goodsCd 계열 hidden input 또는 URL 파라미터\n"
        "- 대표 이미지: 상세 대표 이미지 영역의 img (src/data-src)\n"
        "- 옵션: 옵션 영역의 select\n"
        "- 목록 상품 링크: a[href*='goods_view.php']"
    ),
}


def platform_hint_block(platform: str | None) -> str:
    """플랫폼 힌트 텍스트(+참고용 주의문). 힌트 없으면 빈 문자열."""
    if not platform:
        return ""
    hint = PLATFORM_PROMPT_HINTS.get(platform)
    if not hint:
        return ""
    return hint + _HINT_FOOTER
