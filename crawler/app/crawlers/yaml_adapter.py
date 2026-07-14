from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, AsyncIterator
from urllib.parse import parse_qsl, urljoin, urlparse

from app.analyzer.adapter_schema import (
    Adapter,
    CategoriesConfig,
    FieldExtractor,
    OptionsConfig,
    clean_field_value,
    extract_url_value,
)
from app.analyzer.option_text_parser import (
    parse_option_text,
    is_option_placeholder,
    _legacy_split_option_text_price,
)
from app.credentials.store import load_supplier_credentials
from app.crawlers.base import BaseAdapter, CategoryEntry, CrawlResult, StockSnapshotData
from app.crawlers.engine import PlaywrightEngine
from app.diagnostics import log_exception, sanitize_diagnostic
from app.schema.standard import (
    StandardOption,
    StandardProduct,
    build_option_display_name,
    derive_option_price_delta,
)


logger = logging.getLogger(__name__)


def _extract_number(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"-?\d[\d,]*", text)
    if not match:
        return None
    cleaned = match.group().replace(",", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


def _extract_signed_number(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"([+-]?)\s*([\d,]+)", text)
    if not match:
        return None
    sign = -1 if match.group(1) == "-" else 1
    cleaned = match.group(2).replace(",", "")
    try:
        return sign * int(cleaned)
    except ValueError:
        return None


def _split_option_text_price(text: str | None) -> tuple[str | None, int | None]:
    return _legacy_split_option_text_price(text)


def _category_id_from_url(url: str, fallback: str = "") -> str:
    """카테고리 URL에서 안정적인 id를 뽑는다: 첫 쿼리 파라미터 값(xcode=024&type=O → "024"),
    없으면 마지막 경로 조각, 없으면 fallback. 예전의 '마지막 = 뒤' 방식은 &type=O 같은
    꼬리 파라미터를 집어 모든 카테고리 id가 'O'로 겹쳤다 (선택/수집이 id 세트 기반이라 전멸)."""
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query)
    if pairs and pairs[0][1]:
        return pairs[0][1]
    segment = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    return segment or fallback or url


def _option_price_at(
    price_values: list[int | None],
    total_count: int,
    raw_idx: int,
    accepted_idx: int,
) -> int | None:
    """옵션 가격 배열에서 이 옵션에 해당하는 값을 고른다.

    price_values(option_price_delta multiple)는 보통 placeholder 포함 '전체 요소'에서
    나오는데, 옵션 순회는 placeholder를 걸러 accepted_idx로 센다. 개수가 같으면 원소
    위치(raw_idx)로 집어야 가격이 한 칸씩 밀리지 않는다. 개수가 다르면 accepted_idx 폴백.
    """
    idx = raw_idx if len(price_values) == total_count else accepted_idx
    return price_values[idx] if 0 <= idx < len(price_values) else None


def _first_nonempty_str(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_number(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, int):
            return value
        if value is not None:
            number = _extract_number(str(value))
            if number is not None:
                return number
    return None


def _fill_from_structured(
    name: str | None,
    image: str | None,
    price: int | None,
    sd: dict[str, Any],
) -> tuple[str | None, str | None, int | None]:
    """추출값이 비었을 때만 구조화 데이터(og meta / JSON-LD Product)로 채운다. 순수 함수.

    이름: og:title → JSON-LD name. 이미지: og:image → JSON-LD image(검증은 호출부).
    가격: JSON-LD offers.price → meta product:price:amount.
    """
    if not (name or "").strip():
        name = _first_nonempty_str(sd.get("og_title"), sd.get("ld_name")) or name
    if not (image or "").strip():
        image = _first_nonempty_str(sd.get("og_image"), sd.get("ld_image")) or image
    if price is None:
        price = _first_number(sd.get("ld_price"), sd.get("og_price"))
    return name, image, price


# 상세 페이지의 og meta 3종 + JSON-LD Product(name/image/offers.price)를 한 번에 읽는다.
_STRUCTURED_DATA_JS = r"""
() => {
  const meta = (p) => {
    const el = document.querySelector(`meta[property='${p}']`);
    return el ? (el.getAttribute('content') || null) : null;
  };
  let ldName = null, ldImage = null, ldPrice = null;
  for (const s of document.querySelectorAll("script[type='application/ld+json']")) {
    let data;
    try { data = JSON.parse(s.textContent); } catch (e) { continue; }
    const nodes = Array.isArray(data) ? data : (data['@graph'] || [data]);
    for (const node of nodes) {
      if (!node || typeof node !== 'object') continue;
      const t = node['@type'];
      const isProduct = t === 'Product' || (Array.isArray(t) && t.includes('Product'));
      if (!isProduct) continue;
      if (!ldName && node.name) ldName = String(node.name);
      if (!ldImage && node.image) {
        const img = Array.isArray(node.image) ? node.image[0] : node.image;
        ldImage = (img && typeof img === 'object') ? (img.url || null) : img;
      }
      let offers = node.offers;
      if (Array.isArray(offers)) offers = offers[0];
      if (!ldPrice && offers && offers.price != null) ldPrice = String(offers.price);
    }
  }
  return {
    og_title: meta('og:title'),
    og_image: meta('og:image'),
    og_price: meta('product:price:amount'),
    ld_name: ldName,
    ld_image: ldImage ? String(ldImage) : null,
    ld_price: ldPrice,
  };
}
"""


def _apply_transform(value: str | None, transform: str) -> str | int | None:
    if value is None:
        return None
    if transform == "extract_number":
        return _extract_number(value)
    if transform == "extract_signed_number":
        return _extract_signed_number(value)
    return value.strip() if transform == "strip" else value


def _status_from_maxq_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return "sold_out" if cleaned == "0" else "available"


def _map_supplier_status(status_value: Any, mapping: dict[str, str], default: str) -> str:
    if status_value:
        cleaned = str(status_value).strip()
        if cleaned in {"available", "sold_out", "stopped", "unknown"}:
            return cleaned
        if cleaned in mapping:
            return mapping[cleaned]
        lowered = cleaned.lower()
        for key, value in mapping.items():
            needle = str(key).strip().lower()
            if len(needle) >= 2 and needle in lowered:
                return value
        return default
    return default if default == "available" else "unknown"


# Placeholder/decorative image markers — lazy-load spacers, blank pixels, icons.
_JUNK_IMAGE_RE = re.compile(r"blank|spacer|1x1|no_?image|noimg|transparent|/icon", re.IGNORECASE)
# gif is excluded: on these sites gifs are almost always banners/spacers, not product images.
_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")

# ===== Shared sale-status detection (품절 판정) =====
# 페이지에 붙는 품절 마커: 이미지/텍스트.
SOLDOUT_MARKER_SELECTOR = (
    "img[src*='soldout'], img[src*='sold_out'], img[alt*='품절'], img[alt*='soldout'], "
    ":text('품절'), :text('soldout'), :text('완판')"
)
# 장바구니/구매 버튼 광범위 패턴. 주의: 상단 전역 네비의 주문/장바구니 이미지까지 잡을 수 있어
# 구체 셀렉터가 있으면 그쪽을 우선한다(status_from_cart_button 참고).
CART_BUTTON_SELECTOR = (
    "button:has-text('장바구니'), button:has-text('구매'), button:has-text('주문'), "
    "button:has-text('Buy'), button:has-text('Cart'), "
    "input[type='button'][value*='구매'], input[type='submit'][value*='구매'], "
    "input[type='image'][src*='cart'], input[type='image'][src*='buy'], "
    "img[src*='cart'], img[src*='buy'], img[src*='order'], img[src*='purchase']"
)
SOLDOUT_TEXT_RE = re.compile(r"품절(?!\s*아님)|매진|완판|sold\s*out|재고\s*없", re.IGNORECASE)


def is_soldout_text(text: str | None) -> bool:
    return bool(text) and bool(SOLDOUT_TEXT_RE.search(str(text)))


async def status_from_cart_button(page, specific_selector: str | None) -> str | None:
    """cart_button fallback 판정. 3곳(런타임/미리보기)에서 공유한다.

    품절 마커가 보이면 sold_out. 구체 셀렉터가 지정되면 그 존재 여부로만 판정한다
    (광범위 패턴은 전역 네비를 오탐하므로). 셀렉터가 없으면 광범위 패턴으로 폴백.
    """
    if await page.query_selector(SOLDOUT_MARKER_SELECTOR):
        return "sold_out"
    if specific_selector:
        return "available" if await page.query_selector(specific_selector) else "sold_out"
    return "available" if await page.query_selector(CART_BUTTON_SELECTOR) else None


async def option_is_soldout(element, raw_text: str | None) -> bool:
    """옵션 요소 단위 품절 판정: disabled 속성 / 텍스트 키워드 / class 마커."""
    if is_soldout_text(raw_text):
        return True
    try:
        if await element.get_attribute("disabled") is not None:
            return True
        cls = (await element.get_attribute("class") or "").lower()
        if "soldout" in cls or "sold_out" in cls or "품절" in cls:
            return True
    except Exception:
        pass
    return False


def _is_placeholder_src(value: Any) -> bool:
    """True for empty / data-URI / spacer-style img src used by lazy loaders."""
    if not isinstance(value, str):
        return True
    url = value.strip()
    return not url or url.lower().startswith("data:") or bool(_JUNK_IMAGE_RE.search(url))


def _supported_image_url(value: Any, base_url: str = "") -> str | None:
    """유효한 이미지 URL이면 base_url 기준 절대 URL로 반환. src 속성값은 보통 상대경로다."""
    if not isinstance(value, str):
        return None
    url = value.strip()
    if not url or url.lower().startswith("data:"):
        return None
    if _JUNK_IMAGE_RE.search(url):
        return None
    path = url.split("?", 1)[0].split("#", 1)[0].lower()
    last_segment = path.rsplit("/", 1)[-1]
    # Accept known image extensions, or extensionless CDN/resizer URLs (no "." in the
    # filename part) — collected values already come from <img> src, so they are images.
    if not (path.endswith(_IMAGE_EXT) or "." not in last_segment):
        return None
    return urljoin(base_url, url)


def _image_values(value: Any, base_url: str = "") -> list[str]:
    values = value if isinstance(value, list) else ([value] if value else [])
    return [img for img in (_supported_image_url(item, base_url) for item in values) if img]


# 파일명 크기 토큰: 접미(_s/_m/_l/_t/_th/_small/_medium/_large/_thumb) · 접두(small_/thumb_/th_).
# 숫자 식별부는 건드리지 않아 서로 다른 이미지(103 vs 104)는 다른 키로 남는다.
_SIZE_SUFFIX_RE = re.compile(r"_(?:s|m|l|t|th|small|medium|large|thumb)$", re.IGNORECASE)
_SIZE_PREFIX_RE = re.compile(r"^(?:small|thumb|th)_", re.IGNORECASE)


def _image_key(url: str, base_url: str = "") -> str:
    """크기변형 URL(big/small 폴더, 리사이저 쿼리, _s/_thumb 접미 등)도 같은 이미지로 보도록
    파일명 기준 키. 경로/쿼리 무시 → 사이즈 디렉토리(/small/, /thumb/ 등)는 자연히 동일 키."""
    absolute = urljoin(base_url, url)
    path = absolute.split("?", 1)[0].split("#", 1)[0]
    name = path.rsplit("/", 1)[-1].lower()
    if not name:
        return absolute.lower()
    stem, dot, ext = name.rpartition(".")
    if not dot:  # 확장자 없음 (CDN/리사이저 URL)
        stem = name
    stem = _SIZE_SUFFIX_RE.sub("", stem)
    stem = _SIZE_PREFIX_RE.sub("", stem)
    # ponytail: 크기 토큰이 실제 식별부인 드문 파일명(image_l.jpg가 별개 원본)은 과잉병합될 수 있음
    return f"{stem}.{ext}" if dot else stem


def _without_images(images: list[str], excluded: str | None, base_url: str = "") -> list[str]:
    if not excluded:
        return images
    excluded_key = _image_key(excluded, base_url)
    # ponytail: 파일명 비교 — 다른 폴더에 동일 파일명인 정식 추가이미지가 드물게 같이 제외될 수 있음
    return [img for img in images if _image_key(img, base_url) != excluded_key]


def _image_csv(value: Any) -> str | None:
    images = _image_values(value)
    return ",".join(images) or None


DETAIL_IMAGE_MIN_PX = 300  # ponytail: 튜닝 노브 — 작은 상품썸네일 새면 올리고, 넓은 상세띠 잘리면 내려라

# selector가 가리키는(또는 그 하위) <img>를 브라우저에서 크기 측정 후, '확실히 작은' 것(버튼·화살표·
# 아이콘·스페이서)만 제외. effW = max(naturalWidth, width속성, rect.width) — 두 변 모두 0<크기<min일 때만
# drop. 크기 불명(lazy 미로딩: natural=0/속성없음/rect=0)은 보존.
_COLLECT_IMAGES_JS = r"""
([selector, minPx]) => {
  const PLACEHOLDER = /blank|spacer|1x1|no_?image|noimg|transparent|\/icon/i;
  // 사이드바 퀵메뉴 아이콘·버튼(품절리스트/엑셀주문/적립금충전/채팅 등)은 세로로 길어 크기 필터를
  // 통과할 수 있어 파일명 토큰으로도 제외. 보수적으로 경계 붙은 icon/btn/quick + banner_sm 만.
  const SKIP_SRC = /(?:^|[\/_\-])(?:icon|btn|quick)(?=[\/_\-.]|$)|banner_sm/i;
  const LAZY_ATTRS = ['src', 'data-src', 'data-original', 'data-lazy', 'data-echo'];
  function realSrc(img) {
    // _read_image_attribute와 동일 우선순위 — placeholder/data-URI 건너뛰고 lazy 속성 순회
    for (const attr of LAZY_ATTRS) {
      const v = (img.getAttribute(attr) || '').trim();
      if (v && !v.toLowerCase().startsWith('data:') && !PLACEHOLDER.test(v)) return v;
    }
    const srcset = (img.getAttribute('srcset') || '').trim();
    if (srcset) {
      const first = srcset.split(',')[0].trim().split(/\s+/)[0] || '';
      if (first && !PLACEHOLDER.test(first)) return first;
    }
    return (img.getAttribute('src') || '').trim();  // 전부 placeholder면 raw src로 폴백
  }
  const out = [];
  const seen = {};
  const imgs = [];
  for (const el of document.querySelectorAll(selector)) {
    if (el.tagName === 'IMG') imgs.push(el);
    else for (const img of el.querySelectorAll('img')) imgs.push(img);
  }
  for (const img of imgs) {
    const src = realSrc(img);
    if (!src || seen[src]) continue;
    if (SKIP_SRC.test(src)) continue;  // 아이콘/버튼/퀵메뉴 파일명 토큰 제외
    const attrW = parseInt(img.getAttribute('width') || '0', 10) || 0;
    const attrH = parseInt(img.getAttribute('height') || '0', 10) || 0;
    const rect = img.getBoundingClientRect();
    const effW = Math.max(img.naturalWidth || 0, attrW, Math.round(rect.width) || 0);
    const effH = Math.max(img.naturalHeight || 0, attrH, Math.round(rect.height) || 0);
    if (effW > 0 && effH > 0 && effW < minPx && effH < minPx) continue;  // 버튼/아이콘/스페이서
    seen[src] = 1;
    out.push(src);
  }
  return out;
}
"""


async def collect_detail_images(page, selector: str, min_px: int = DETAIL_IMAGE_MIN_PX) -> list[str]:
    """selector가 가리키는(또는 하위) <img>의 src/data-src 중 '확실히 작은' 버튼류만 제외해 반환.

    크롤·테스트 경로가 공유 — page.evaluate 한 번으로 측정+수집을 원자적으로 수행한다.
    """
    try:
        result = await page.evaluate(_COLLECT_IMAGES_JS, [selector, min_px])
        return [str(item) for item in (result or [])]
    except Exception:
        return []


class YAMLAdapter(BaseAdapter):
    def __init__(
        self,
        adapter: Adapter,
        engine: PlaywrightEngine,
        supplier_name: str,
        delay_seconds: int = 0,
        supplier_slug: str | None = None,
    ) -> None:
        self.adapter = adapter
        self.engine = engine
        self.supplier_name = supplier_name
        self.supplier_slug = supplier_slug
        self.delay_seconds = delay_seconds
        self._login_failure_reason = ""

    async def _perform_login(self, page) -> bool:
        """Perform login if the adapter requires it. Returns True if login succeeded or not needed.
        On failure sets self._login_failure_reason with a specific, user-facing cause."""
        self._login_failure_reason = ""
        login_config = self.adapter.adapter.login
        if not login_config.required or not login_config.login_url:
            return True

        # Try to load credentials from keyring
        if not self.supplier_slug:
            self._login_failure_reason = "로그인 정보 키가 없습니다. 도매처를 다시 저장하세요."
            logger.warning("login skipped: missing supplier credential key supplier=%s", self.supplier_name)
            return False
        creds = load_supplier_credentials(self.supplier_slug)
        if not creds:
            self._login_failure_reason = (
                "저장된 로그인 아이디/비밀번호가 없습니다. 도매처 편집에서 로그인 정보를 다시 입력하세요."
            )
            logger.warning("login skipped: missing credentials supplier=%s", self.supplier_name)
            return False
        username, password = creds

        try:
            logger.info("login started supplier=%s url=%s", self.supplier_name, login_config.login_url)
            await page.goto(login_config.login_url, wait_until="domcontentloaded", timeout=15_000)
            await page.wait_for_timeout(1500)

            # 설정된 로그인 입력란 선택자를 우선 시도하되, 페이지에 없으면 자동 감지로
            # 폴백한다 (생성 오류/사이트 변경으로 선택자가 어긋나도 로그인되도록).
            auto_id = "input[type='text'], input[type='email'], input[name*='id'], input[name*='user'], input[name*='member']"
            auto_pw = "input[type='password']"
            id_el = pw_el = None
            if login_config.fields and login_config.fields.id and login_config.fields.password:
                id_el = await page.query_selector(login_config.fields.id)
                pw_el = await page.query_selector(login_config.fields.password)
            if not id_el:
                id_el = await page.query_selector(auto_id)
            if not pw_el:
                pw_el = await page.query_selector(auto_pw)
            if not id_el or not pw_el:
                self._login_failure_reason = (
                    "로그인 입력란(아이디/비밀번호)을 찾지 못했습니다. 로그인 페이지 주소가 맞는지, "
                    "입력란 선택자가 맞는지 확인하세요."
                )
                return False
            await id_el.fill(username)
            await pw_el.fill(password)

            # 제출 버튼: 설정된 것을 우선, 없거나 못 찾으면 일반 선택자 → Enter로 폴백
            submit_el = None
            if login_config.submit:
                submit_el = await page.query_selector(login_config.submit)
            if not submit_el:
                for sel in ["button[type='submit']", "input[type='submit']", ".login-btn",
                            "button:has-text('로그인')", "input[type='image']"]:
                    try:
                        submit_el = await page.query_selector(sel)
                    except Exception:
                        submit_el = None
                    if submit_el:
                        break
            if submit_el:
                await submit_el.click()
            else:
                await pw_el.press("Enter")

            await page.wait_for_timeout(3000)

            # Check success
            if login_config.success_indicator:
                success_el = await page.query_selector(login_config.success_indicator)
                logger.info("login finished supplier=%s success=%s", self.supplier_name, success_el is not None)
                if success_el is None:
                    self._login_failure_reason = (
                        f"로그인을 시도했으나 성공을 확인하지 못했습니다 (성공 지표: "
                        f"{login_config.success_indicator}). 아이디/비밀번호가 맞는지, "
                        f"성공 지표 선택자가 맞는지 확인하세요."
                    )
                return success_el is not None

            # Check common logout indicators
            for sel in ["a[href*='logout']", "img[src*='logout']", "a:has-text('로그아웃')"]:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        return True
                except Exception:
                    continue

            # If no failure indicator found, assume success
            if login_config.failure_indicator:
                fail_el = await page.query_selector(login_config.failure_indicator)
                if fail_el:
                    logger.info("login finished supplier=%s success=False", self.supplier_name)
                    return False

            logger.info("login finished supplier=%s success=True", self.supplier_name)
            return True
        except Exception as exc:
            self._login_failure_reason = f"로그인 중 오류: {sanitize_diagnostic(exc)}"
            log_exception(logger, f"login failed supplier={self.supplier_name}", exc)
            return False

    async def discover_categories(self) -> list[CategoryEntry]:
        config = self.adapter.adapter.categories
        # 마법사가 확정해 저장한 카테고리 목록이 있으면 그대로 사용한다 (menu_selector로
        # 매번 다시 걷지 않음 — 사용자가 화면에서 본 것과 정확히 일치).
        if getattr(config, "entries", None):
            entries: list[CategoryEntry] = []
            seen_ids: set[str] = set()
            for item in config.entries:
                if not item.url:
                    continue
                cat_id = _category_id_from_url(item.url, item.name)
                if cat_id in seen_ids:
                    cat_id = item.url  # id 충돌 시 URL로 유일성 보장 — 중복 id는 선택/수집에서 통째로 누락됨
                seen_ids.add(cat_id)
                entries.append(CategoryEntry(
                    category_id=cat_id,
                    name=item.name or item.url,
                    path=item.name or item.url,
                    url=item.url,
                ))
            return entries
        if config.mode == "all_products" or (config.mode == "hybrid" and config.all_products.available):
            if config.all_products.url:
                return [CategoryEntry(
                    category_id="__all__",
                    name="전체 상품",
                    path="전체 상품",
                    url=config.all_products.url,
                )]

        nav = config.navigation
        if not nav:
            return []

        page = await self.engine.new_page()
        try:
            await page.goto(self.adapter.adapter.base_url, wait_until=self.adapter.adapter.browser.wait_until)
            return await self._walk_menu(page, nav.menu_selector, nav, depth=1, parent_path="")
        finally:
            await page.close()

    async def _walk_menu(self, page, selector: str, nav, depth: int, parent_path: str) -> list[CategoryEntry]:
        entries: list[CategoryEntry] = []
        items = await page.query_selector_all(selector)
        for item in items:
            link = await item.query_selector(nav.link_selector)
            if not link:
                continue
            name_text = await link.get_attribute(nav.url_attribute) if nav.name_source == "attribute" else await link.inner_text()
            if not name_text:
                continue
            name = name_text.strip()
            href = await link.get_attribute(nav.url_attribute)
            if not href:
                continue
            url = urljoin(self.adapter.adapter.base_url, href)
            cat_id = _category_id_from_url(url, name)
            path = f"{parent_path} > {name}" if parent_path else name

            entry = CategoryEntry(category_id=cat_id, name=name, path=path, url=url)

            if depth < nav.max_depth and nav.submenu:
                try:
                    if nav.submenu.expand_trigger == "hover":
                        await item.hover()
                        await page.wait_for_timeout(500)
                    elif nav.submenu.expand_trigger == "click":
                        await link.click()
                        await page.wait_for_timeout(500)
                    sub_items = await item.query_selector_all(nav.submenu.selector)
                    if sub_items:
                        children = await self._walk_subitems(page, sub_items, nav, depth + 1, path)
                        entry.children = children
                except Exception:
                    pass

            entries.append(entry)
        return entries

    async def _walk_subitems(self, page, subitems, nav, depth: int, parent_path: str) -> list[CategoryEntry]:
        entries: list[CategoryEntry] = []
        for sub in subitems:
            name_text = await sub.inner_text()
            if not name_text:
                continue
            name = name_text.strip()
            href = await sub.get_attribute(nav.url_attribute)
            if not href:
                continue
            url = urljoin(self.adapter.adapter.base_url, href)
            cat_id = _category_id_from_url(url, name)
            path = f"{parent_path} > {name}"
            entries.append(CategoryEntry(category_id=cat_id, name=name, path=path, url=url))
        return entries

    def _listing_url(self, category_id: str | None, category_url: str | None, page_num: int) -> str:
        """카테고리 리스팅 페이지 URL을 만든다.
        1) url_template이 있으면 {category_id}/{page}로 채운다.
        2) 없으면 discovery가 찾은 실제 카테고리 URL(category_url)을 쓰고,
           2페이지 이후는 page_param을 붙여 페이지네이션한다.
        3) 그래도 없으면 category_id를 URL로 간주(구버전 호환)."""
        config = self.adapter.adapter
        template = config.categories.url_template
        if template:
            return template.format(category_id=category_id, page=page_num)
        base = category_url or category_id or ""
        pagination = config.listing.pagination
        if base and page_num > pagination.start:
            param = pagination.page_param or "page"
            sep = "&" if "?" in base else "?"
            return f"{base}{sep}{param}={page_num}"
        return base

    async def crawl_category(
        self,
        category_id: str,
        max_pages: int,
        category_url: str | None = None,
    ) -> AsyncIterator[CrawlResult]:
        config = self.adapter.adapter
        pagination = config.listing.pagination

        # Perform login if needed
        login_config = self.adapter.adapter.login
        if login_config.required:
            login_page = await self.engine.new_page()
            try:
                login_ok = await self._perform_login(login_page)
                if not login_ok:
                    raise RuntimeError(self._login_failure_reason or "도매처 로그인에 실패했습니다. 도매처 편집에서 로그인 정보를 확인하세요.")
            finally:
                await login_page.close()

        seen_links: set[str] = set()
        page_num = pagination.start
        while page_num <= max_pages:
            list_url = self._listing_url(category_id, category_url, page_num)
            if not list_url:
                break

            page = await self.engine.new_page()
            try:
                logger.info("crawl list page supplier=%s category=%s page=%d url=%s", self.supplier_name, category_id, page_num, list_url)
                await page.goto(list_url, wait_until=config.browser.wait_until)
                if pagination.stop_indicator:
                    stop = await page.query_selector(pagination.stop_indicator)
                    if stop:
                        break

                product_links = await self._extract_product_links(page)
                # 이미 본 링크만 나오면(사이트가 page 파라미터를 무시하고 같은 목록을
                # 반복) 페이지네이션 종료 — 같은 상품을 max_pages번 재수집하는 것 방지.
                new_links = [u for u in product_links if u not in seen_links]
                logger.info("crawl list links supplier=%s category=%s page=%d links=%d new=%d", self.supplier_name, category_id, page_num, len(product_links), len(new_links))
                if not new_links:
                    break
                seen_links.update(new_links)

                for link_url in new_links:
                    result = await self._crawl_product(link_url, category_path=category_id)
                    if result:
                        yield result
                    if self.delay_seconds > 0:
                        await asyncio.sleep(self.delay_seconds)
            finally:
                await page.close()

            if self.delay_seconds > 0:
                await asyncio.sleep(self.delay_seconds)
            page_num += 1

    async def _extract_product_links(self, page) -> list[str]:
        link_config = self.adapter.adapter.listing.product_link
        elements = await page.query_selector_all(link_config.selector)
        links: list[str] = []
        for el in elements:
            href = await el.get_attribute(link_config.attribute)
            if not href:
                continue
            url = urljoin(self.adapter.adapter.base_url, href)
            links.append(url)
        return links

    async def _crawl_product(self, url: str, category_path: str) -> CrawlResult | None:
        page = await self.engine.new_page()
        try:
            logger.info("crawl product supplier=%s url=%s", self.supplier_name, url)
            await page.goto(url, wait_until=self.adapter.adapter.browser.wait_until)
            product_config = self.adapter.adapter.product

            fields: dict[str, Any] = {}
            for field_name in ("supplier_product_id", "supplier_product_code", "raw_product_name",
                               "supply_price", "origin", "main_image_url", "detail_content",
                               "extra_image_urls", "brand_name", "manufacturer", "model_name"):
                extractor: FieldExtractor | None = getattr(product_config, field_name, None)
                if extractor is None or extractor.optional is False and not extractor.selector:
                    fields[field_name] = None
                    continue
                fields[field_name] = await self._extract_field(page, extractor, field_name)

            status_value = None
            if product_config.supplier_status:
                status_value = await self._extract_field(page, product_config.supplier_status)
            status_mapping = product_config.status_mapping.mapping
            mapped_status = _map_supplier_status(status_value, status_mapping, product_config.status_mapping.default)

            supply_price_raw = fields.get("supply_price")
            supply_price = _extract_number(str(supply_price_raw)) if isinstance(supply_price_raw, str) else supply_price_raw

            raw_name = str(fields.get("raw_product_name") or "").strip()
            main_image = _supported_image_url(fields.get("main_image_url"), page.url)

            # 선택자가 비면 상세 페이지의 og meta / JSON-LD로 폴백(하나라도 비었을 때만 조회).
            if not raw_name or not main_image or supply_price is None:
                sd = await self._structured_data(page)
                raw_name, sd_image, supply_price = _fill_from_structured(
                    raw_name, main_image, supply_price, sd
                )
                if not main_image and sd_image:
                    main_image = _supported_image_url(sd_image, page.url)

            detail_images = _without_images(_image_values(fields.get("detail_content"), page.url), main_image, page.url)
            detail = ",".join(detail_images) or None

            extra_images = _without_images(_image_values(fields.get("extra_image_urls"), page.url), main_image, page.url)

            raw_meta: dict[str, Any] = {
                "url": url,
                "supplier_product_id": fields.get("supplier_product_id"),
                "supplier_product_code": fields.get("supplier_product_code"),
                "raw_product_name": fields.get("raw_product_name"),
                "supply_price_raw": fields.get("supply_price"),
                "status_raw": status_value,
            }

            product = StandardProduct(
                supplier_name=self.supplier_name,
                supplier_product_id=str(fields.get("supplier_product_id") or "").strip() or None,
                supplier_product_code=str(fields.get("supplier_product_code") or "").strip() or url,
                supplier_status=mapped_status,
                raw_product_name=raw_name or "이름 없음",
                origin=str(fields.get("origin") or "").strip() or None if isinstance(fields.get("origin"), str) else fields.get("origin"),
                supply_price=supply_price,
                main_image_url=main_image if isinstance(main_image, str) else None,
                detail_content=detail,
                supplier_category=category_path,
                extra_image_urls=extra_images,
                brand_name=str(fields.get("brand_name")).strip() if fields.get("brand_name") else None,
                manufacturer=str(fields.get("manufacturer")).strip() if fields.get("manufacturer") else None,
                model_name=str(fields.get("model_name")).strip() if fields.get("model_name") else None,
                raw_metadata=raw_meta,
            )

            options = await self._extract_options(page, product.supplier_product_code, supply_price)
            logger.info(
                "crawl product extracted supplier=%s code=%s options=%d",
                self.supplier_name,
                product.supplier_product_code,
                len(options),
            )
            return CrawlResult(product=product, options=options)
        except Exception as exc:
            log_exception(logger, f"crawl product failed supplier={self.supplier_name} url={url}", exc)
            raise
        finally:
            await page.close()

    async def _structured_data(self, page) -> dict[str, Any]:
        """상세 페이지의 og meta 3종 + JSON-LD Product를 page.evaluate 한 번으로 읽는다.
        브라우저 실패 시 빈 dict — 폴백은 있으면 좋은 보강일 뿐이라 크롤을 막지 않는다."""
        try:
            result = await page.evaluate(_STRUCTURED_DATA_JS)
            return result or {}
        except Exception:
            return {}

    async def _extract_field(self, page, extractor: FieldExtractor, field_name: str = "") -> Any:
        try:
            if extractor.selector:
                if extractor.multiple:
                    if extractor.attribute in ("src", "data-src"):
                        # 이미지 필드(상세/추가 이미지): 크기 측정으로 버튼·아이콘·스페이서 제외.
                        # collect_detail_images가 selector 자신과 하위 img를 모두 커버하므로 폴백 불필요.
                        values = await collect_detail_images(page, extractor.selector)
                    else:
                        values = await self._read_elements(page, extractor.selector, extractor)
                    if extractor.skip_first:
                        values = values[extractor.skip_first:]
                    if values:
                        return values
                else:
                    element = await page.query_selector(extractor.selector)
                    if element:
                        raw = await self._read_element(element, extractor)
                        if raw:
                            # 라벨 오염 정리(원산지/이름/코드 등)를 transform 전에 적용.
                            raw = clean_field_value(field_name, raw)
                            if raw:
                                return _apply_transform(raw, extractor.transform)

            fallback_value = await self._extract_field_fallback_from(page, extractor)
            if fallback_value is not None:
                return _apply_transform(fallback_value, extractor.transform)
            if extractor.fallback:
                return _apply_transform(extractor.fallback, extractor.transform)
            return None
        except Exception as exc:
            logger.warning("field extraction failed selector=%s: %s", extractor.selector, exc)
            if extractor.fallback:
                return _apply_transform(extractor.fallback, extractor.transform)
            return None

    async def _read_elements(self, page, selector: str, extractor: FieldExtractor) -> list[str]:
        elements = await page.query_selector_all(selector)
        values: list[str] = []
        for el in elements:
            val = await self._read_element(el, extractor)
            if val:
                values.append(val)
        return values

    async def _extract_field_fallback_from(self, page, extractor: FieldExtractor) -> str | None:
        if extractor.fallback_from == "url":
            return extract_url_value(page.url, extractor)

        if extractor.fallback_from == "maxq":
            maxq = await page.query_selector("input[name='maxq']")
            if not maxq:
                return None
            return _status_from_maxq_value(await maxq.get_attribute("value"))

        if extractor.fallback_from == "cart_button":
            return await status_from_cart_button(page, extractor.selector)

        return None

    async def _read_element(self, element, extractor: FieldExtractor) -> str | None:
        if extractor.html:
            return await element.inner_html()
        if extractor.attribute:
            if extractor.attribute in ("src", "data-src"):
                return await self._read_image_attribute(element, extractor)
            value = await element.get_attribute(extractor.attribute)
            if not value and extractor.fallback_attribute:
                value = await element.get_attribute(extractor.fallback_attribute)
            return value
        return await element.inner_text()

    async def _read_image_attribute(self, element, extractor: FieldExtractor) -> str | None:
        """Resolve a lazy-loaded image URL: skip placeholder src, try common lazy attrs."""
        attrs = [extractor.attribute, extractor.fallback_attribute,
                 "data-src", "data-original", "data-lazy", "data-echo"]
        first_non_placeholder = None
        for attr in attrs:
            if not attr:
                continue
            value = await element.get_attribute(attr)
            if not value:
                continue
            if _is_placeholder_src(value):
                continue
            first_non_placeholder = first_non_placeholder or value.strip()
        if first_non_placeholder:
            return first_non_placeholder
        srcset = await element.get_attribute("srcset")
        if srcset:
            first = srcset.strip().split(",", 1)[0].split()[0] if srcset.strip() else ""
            if first and not _is_placeholder_src(first):
                return first
        # Everything was a placeholder — fall back to raw src so extraction isn't empty.
        return await element.get_attribute(extractor.attribute)

    async def _extract_options(self, page, product_code: str, base_price: int | None) -> list[StandardOption]:
        config = self.adapter.adapter.options
        # 옵션 선택자가 매핑돼 있으면 수집한다. detection 플래그는 groups와 중복이라 게이트로 쓰지 않는다
        # (LLM 생성 YAML이 detection: none으로 남겨두는 바람에 매핑된 옵션이 통째로 누락됐다).
        if not any(group.values_selector.strip() for group in config.groups):
            return []

        if config.dependent_options.enabled:
            return await self._extract_dependent_options(page, config, product_code, base_price)

        options: list[StandardOption] = []
        price_values: list[int | None] = []
        if config.option_price_delta and config.option_price_delta.multiple:
            price_raw = await self._extract_field(page, config.option_price_delta)
            if isinstance(price_raw, list):
                price_values = [
                    _extract_number(str(item)) if not isinstance(item, int) else item
                    for item in price_raw
                ]
        for group_config in config.groups:
            values = await page.query_selector_all(group_config.values_selector)
            total_count = len(values)
            accepted_index = 0
            for raw_idx, el in enumerate(values):
                raw_value_text = await self._read_option_value(el, group_config)
                parsed_text = parse_option_text(raw_value_text, config.option_text_parser, base_price)
                value_text = parsed_text.value
                if not value_text:
                    continue
                option_data = {
                    "option_group_1": group_config.name,
                    "option_value_1": value_text,
                    "option_value_2": None,
                    "option_value_3": None,
                }
                price_delta = None
                option_supply = None
                if price_values:
                    option_supply = _option_price_at(price_values, total_count, raw_idx, accepted_index)
                    price_delta = derive_option_price_delta(option_supply, base_price)
                elif config.option_price_delta:
                    price_delta_raw = await self._extract_field(page, config.option_price_delta)
                    price_delta = _extract_signed_number(str(price_delta_raw)) if isinstance(price_delta_raw, str) else price_delta_raw
                    option_supply = (base_price or 0) + (price_delta or 0) if base_price else None
                elif parsed_text.price_delta is not None or parsed_text.supply_price is not None:
                    price_delta = parsed_text.price_delta
                    option_supply = parsed_text.supply_price
                image_url = None
                if config.option_image_url:
                    image_url = _supported_image_url(
                        await self._extract_field(page, config.option_image_url), page.url
                    )

                stock = None
                if config.option_stock_quantity:
                    stock_raw = await self._extract_field(page, config.option_stock_quantity)
                    stock = _extract_number(str(stock_raw)) if isinstance(stock_raw, str) else stock_raw

                # ponytail: 옵션 요소 자체 신호(disabled/텍스트 (품절)/class)로 자동 감지.
                # 자식 배지로만 표기하는 희귀 몰은 OptionsConfig에 마커 셀렉터 추가로 확장.
                sold = await option_is_soldout(el, raw_value_text)

                options.append(StandardOption(
                    supplier_product_code=product_code,
                    option_sku=f"{product_code}-{accepted_index + 1}" if product_code else None,
                    option_type=config.type,
                    option_group_1=group_config.name,
                    option_value_1=value_text,
                    option_group_2=None,
                    option_value_2=None,
                    option_group_3=None,
                    option_value_3=None,
                    option_display_name=build_option_display_name(option_data),
                    option_supply_price=option_supply,
                    option_sale_price=None,
                    option_price_delta=price_delta,
                    option_stock_quantity=stock,
                    option_status="sold_out" if sold else None,
                    option_usable=not sold,
                    option_main_image_url=image_url if isinstance(image_url, str) else None,
                    option_extra_image_urls=[],
                    option_position=accepted_index + 1,
                    raw_option_text=raw_value_text,
                    raw_option_metadata={"group": group_config.name, "value": value_text},
                ))
                accepted_index += 1
        return options

    async def _extract_dependent_options(
        self, page, config: OptionsConfig, product_code: str, base_price: int | None
    ) -> list[StandardOption]:
        dep = config.dependent_options
        if not config.groups or not dep.level_2_values_selector:
            return []

        level1_config = config.groups[0]
        level1_elements = await page.query_selector_all(level1_config.values_selector)
        # (raw_idx, 값) — placeholder("- 선택하세요 -" 등) 제외. raw_idx로 매 반복 재질의해
        # 클릭 후 stale 핸들과 따옴표 이스케이프 문제를 함께 회피한다.
        level1_values: list[tuple[int, str]] = []
        for idx, el in enumerate(level1_elements):
            value_text = await self._read_option_value(el, level1_config)
            if value_text and value_text.strip() and not is_option_placeholder(value_text):
                level1_values.append((idx, value_text.strip()))

        options: list[StandardOption] = []
        position = 1
        for raw_idx, l1_value in level1_values:
            try:
                current = await page.query_selector_all(level1_config.values_selector)
                if raw_idx < len(current):
                    level1_el = current[raw_idx]
                    if dep.level_2_trigger == "click":
                        await level1_el.click()
                    elif dep.level_2_trigger == "select":
                        await self._select_dependent_level1(level1_el, l1_value)
                    if dep.level_2_load_indicator:
                        try:
                            await page.wait_for_selector(dep.level_2_load_indicator, timeout=5000)
                            await page.wait_for_selector(dep.level_2_load_indicator, state="detached", timeout=5000)
                        except Exception:
                            pass
                    else:
                        await page.wait_for_timeout(800)
                level2_elements = await page.query_selector_all(dep.level_2_values_selector)
                for l2_el in level2_elements:
                    l2_value = await l2_el.inner_text()
                    if not l2_value.strip() or is_option_placeholder(l2_value):
                        continue
                    l2_value = l2_value.strip()
                    l2_sold = await option_is_soldout(l2_el, l2_value)
                    option_data = {
                        "option_group_1": dep.level_1_group or level1_config.name,
                        "option_value_1": l1_value,
                        "option_group_2": dep.level_2_group,
                        "option_value_2": l2_value,
                        "option_value_3": None,
                    }
                    options.append(StandardOption(
                        supplier_product_code=product_code,
                        option_sku=f"{product_code}-{position}" if product_code else None,
                        option_type="combination",
                        option_group_1=dep.level_1_group or level1_config.name,
                        option_value_1=l1_value,
                        option_group_2=dep.level_2_group,
                        option_value_2=l2_value,
                        option_group_3=None,
                        option_value_3=None,
                        option_display_name=build_option_display_name(option_data),
                        option_supply_price=base_price,
                        option_sale_price=None,
                        option_price_delta=derive_option_price_delta(base_price, base_price),
                        option_stock_quantity=None,
                        option_status="sold_out" if l2_sold else None,
                        option_usable=not l2_sold,
                        option_main_image_url=None,
                        option_extra_image_urls=[],
                        option_position=position,
                        raw_option_text=f"{l1_value} / {l2_value}",
                        raw_option_metadata={"level1": l1_value, "level2": l2_value},
                    ))
                    position += 1
            except Exception:
                continue
        return options

    async def _select_dependent_level1(self, element, label: str) -> None:
        """의존 옵션 level-1 선택. 요소가 <select>면 select_option, <option> 등이면
        부모 <select>에 값 설정 + change 이벤트를 직접 발생시킨다(option.select_option은 없음)."""
        tag = str(await element.evaluate("el => el.tagName") or "").upper()
        if tag == "SELECT":
            await element.select_option(label=label)
            return
        await element.evaluate(
            "el => { const s = el.closest('select');"
            " if (s) { s.value = el.value;"
            " s.dispatchEvent(new Event('change', {bubbles:true})); } }"
        )

    async def _read_option_value(self, element, group_config) -> str | None:
        if group_config.value_text == "value":
            return await element.get_attribute("value")
        if group_config.value_text == "attribute" and group_config.value_attribute:
            return await element.get_attribute(group_config.value_attribute)
        return await element.inner_text()

    async def stock_check(
        self,
        category_id: str | None = None,
        category_url: str | None = None,
    ) -> AsyncIterator[StockSnapshotData]:
        config = self.adapter.adapter
        pagination = config.listing.pagination

        # Perform login if needed
        login_config = self.adapter.adapter.login
        if login_config.required:
            login_page = await self.engine.new_page()
            try:
                login_ok = await self._perform_login(login_page)
                if not login_ok:
                    raise RuntimeError(self._login_failure_reason or "도매처 로그인에 실패했습니다. 도매처 편집에서 로그인 정보를 확인하세요.")
            finally:
                await login_page.close()

        seen_links: set[str] = set()
        page_num = pagination.start
        while page_num <= pagination.max_pages:
            list_url = self._listing_url(category_id, category_url, page_num)
            if not list_url:
                break

            page = await self.engine.new_page()
            try:
                await page.goto(list_url, wait_until=config.browser.wait_until)
                product_links = await self._extract_product_links(page)
                new_links = [u for u in product_links if u not in seen_links]
                if not new_links:
                    break
                seen_links.update(new_links)

                for link_url in new_links:
                    snapshot = await self._stock_check_product(link_url)
                    if snapshot:
                        yield snapshot
                    if self.delay_seconds > 0:
                        await asyncio.sleep(self.delay_seconds)
            finally:
                await page.close()
            page_num += 1

    async def _stock_check_product(self, url: str) -> StockSnapshotData | None:
        page = await self.engine.new_page()
        try:
            await page.goto(url, wait_until=self.adapter.adapter.browser.wait_until)
            product_config = self.adapter.adapter.product

            status_value = None
            if product_config.supplier_status:
                status_value = await self._extract_field(page, product_config.supplier_status)
            status_mapping = product_config.status_mapping.mapping
            mapped_status = _map_supplier_status(status_value, status_mapping, product_config.status_mapping.default)

            price = None
            if product_config.supply_price:
                price_raw = await self._extract_field(page, product_config.supply_price)
                price = _extract_number(str(price_raw)) if isinstance(price_raw, str) else price_raw
            if price is None:
                sd = await self._structured_data(page)
                price = _first_number(sd.get("ld_price"), sd.get("og_price"))

            code = url
            if product_config.supplier_product_code:
                code_raw = await self._extract_field(page, product_config.supplier_product_code, "supplier_product_code")
                if code_raw and isinstance(code_raw, str):
                    code = code_raw.strip()

            return StockSnapshotData(
                supplier_product_code=code,
                supplier_status=mapped_status,
                supply_price=price,
            )
        except Exception as exc:
            logger.warning("stock product failed supplier=%s url=%s: %s", self.supplier_name, url, exc)
            return None
        finally:
            await page.close()

    async def close(self) -> None:
        pass
