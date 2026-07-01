from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urljoin

from app.analyzer.html_reducer import reduce_html
from app.analyzer.login_helper import _check_logout_indicators, _safe_goto, perform_login


@dataclass
class ProbeResult:
    main_url: str
    final_url: str
    encoding: str
    needs_login: bool
    login_form_html: str
    listing_html: str
    detail_html: str
    sample_links: list[str] = field(default_factory=list)
    ajax_requests: list[dict[str, str]] = field(default_factory=list)
    category_menu_html: str = ""
    has_all_products: bool = False
    categories: list[dict] = field(default_factory=list)  # [{"name": "신상품", "url": "/shop/shopbrand.html?xcode=004"}]
    sample_products: list[dict] = field(default_factory=list)  # [{"url": "...", "image_url": "...", "name": "..."}]
    total_product_count: int | None = None
    products_per_page: int | None = None
    total_pages: int | None = None
    status_indicators: dict = field(default_factory=dict)  # {"has_cart_button": bool, "has_soldout_image": bool, "maxq_value": str, "has_explicit_status": bool}
    login_url: str = ""
    storage_state: dict | None = None


def normalize_sample_products(base_url: str, products: list[dict], links: list[str] | None = None, limit: int = 15) -> tuple[list[dict], list[str]]:
    """Normalize, score, and deduplicate probe sample product links."""
    candidates: list[dict] = []
    for product in products:
        href = str(product.get("url") or "").strip()
        if href:
            item = dict(product)
            item["url"] = urljoin(base_url, href)
            if item.get("image_url"):
                item["image_url"] = urljoin(base_url, str(item["image_url"]).strip())
            candidates.append(item)
    for href in links or []:
        if str(href).strip():
            candidates.append({"url": urljoin(base_url, str(href).strip()), "image_url": "", "name": ""})

    def score(item: dict) -> int:
        name = str(item.get("name") or "").strip()
        return (2 if item.get("image_url") else 0) + (1 if name and name != "(이름 없음)" else 0)

    seen: set[str] = set()
    normalized: list[dict] = []
    for item in sorted(candidates, key=score, reverse=True):
        url = item["url"]
        if url in seen:
            continue
        seen.add(url)
        item["name"] = str(item.get("name") or "").strip() or "(이름 없음)"
        item["image_url"] = str(item.get("image_url") or "").strip()
        normalized.append(item)
        if len(normalized) >= limit:
            break
    return normalized, [item["url"] for item in normalized]


ProgressCallback = Callable[[str], None]


async def probe_site(
    main_url: str,
    sample_listing_url: str | None = None,
    sample_detail_url: str | None = None,
    headless: bool = True,
    on_progress: ProgressCallback | None = None,
    login_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> ProbeResult:
    def _log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    async def _analyze_login_with_llm(page) -> dict[str, str] | None:
        """Use LLM to analyze the login page HTML and extract form selectors."""
        import json
        from app.analyzer.llm_client import get_llm_client
        from app.config import load_config

        # Collect main page + iframe HTML
        parts: list[str] = []
        try:
            parts.append(await page.content())
        except Exception:
            pass
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                iframe_html = await frame.content()
                if iframe_html and iframe_html.strip():
                    parts.append(f"\n<!-- IFRAME CONTENT -->\n{iframe_html}")
            except Exception:
                continue
        html = "\n".join(parts)[:20000]
        if not html or not html.strip():
            return None

        config = load_config()
        provider = config.llm_provider
        client = get_llm_client(provider)

        system_prompt = (
            "당신은 웹 페이지에서 로그인 폼을 분석하는 전문가입니다. "
            "주어진 HTML에서 로그인 폼의 아이디 입력 필드, 비밀번호 입력 필드, "
            "제출 버튼의 CSS 선택자를 추출하세요.\n\n"
            "반드시 다음 JSON 형식으로만 응답하세요:\n"
            '{"id_selector": "CSS선택자", "password_selector": "CSS선택자", "submit_selector": "CSS선택자"}\n\n'
            "규칙:\n"
            "1. input[type='text'], input[type='email'], input[name*='id'] 등이 아이디 필드입니다.\n"
            "2. input[type='password']가 비밀번호 필드입니다.\n"
            "3. button[type='submit'], input[type='submit'], input[type='image'], "
            "a:has-text('로그인'), a[href*='check'] 등이 제출 버튼입니다.\n"
            "4. iframe 내부에 폼이 있을 수 있습니다. iframe 내부 요소도 CSS 선택자로 표현하세요.\n"
            "5. 선택자는 구체적이고 고유해야 합니다 (id, name, type 속성 활용).\n"
            "6. JSON 외의 다른 텍스트는 출력하지 마세요."
        )
        user_prompt = f"다음은 로그인 페이지의 HTML입니다:\n\n{html}"

        response = await client.generate(system_prompt, user_prompt)

        # Strip markdown code fences if present
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            text = "\n".join(lines[1:end])
        text = text.strip()

        result = json.loads(text)
        config_out: dict[str, str] = {}
        for key in ("id_selector", "password_selector", "submit_selector"):
            val = result.get(key, "")
            if val and isinstance(val, str):
                config_out[key] = val
        return config_out or None

    _log("브라우저 시작 중...")
    from app.crawlers.engine import create_engine

    async def _do_probe() -> ProbeResult:
        async with create_engine(headless=headless) as engine:
            page = await engine.new_page()

            requests_log: list[dict[str, str]] = []

            def on_request(request: Any) -> None:
                try:
                    if request.resource_type in ("xhr", "fetch"):
                        requests_log.append({
                            "url": request.url,
                            "method": request.method,
                            "resource_type": request.resource_type,
                        })
                except Exception:
                    pass

            page.on("request", on_request)

            # Login if credentials provided
            storage_state: dict | None = None
            if login_url and username and password:
                success = False
                try:
                    success = await perform_login(page, login_url, username, password, on_progress=_log)
                except Exception as exc:
                    _log(f"1차 로그인 시도 실패: {exc}")
                    success = False
                if not success:
                    # Auto-login failed: try LLM-assisted analysis before giving up.
                    _log("AI가 로그인 페이지 분석 중...")
                    try:
                        llm_login_config = await _analyze_login_with_llm(page)
                        if llm_login_config:
                            _log("AI 분석 완료 — 추출된 선택자로 재시도 중...")
                            try:
                                success = await perform_login(
                                    page, login_url, username, password,
                                    login_config=llm_login_config, on_progress=_log,
                                )
                            except Exception as exc:
                                _log(f"AI 선택자 로그인 실패: {exc}")
                                success = False
                    except Exception as llm_exc:
                        _log(f"AI 분석 실패: {llm_exc}")
                if not success:
                    _log("로그인에 실패했습니다. 로그인 URL과 계정 정보를 확인하세요.")
                    raise RuntimeError("로그인에 실패했습니다. 로그인 URL과 계정 정보를 확인하세요.")
                # 로그인 성공 검증 후 storage_state 추출 (매핑/테스트 단계 세션 공유)
                try:
                    verified = await _check_logout_indicators(page)
                    if not verified:
                        pw = await page.query_selector("input[type='password']")
                        if pw is None:
                            verified = True
                    if verified:
                        storage_state = await page.context.storage_state()
                        _log("로그인 세션 저장됨 (storage_state 추출)")
                    else:
                        _log("로그인 성공 여부 미확인 — 세션 저장 생략")
                except Exception:
                    pass

            _log(f"사이트 접속 중: {main_url}")
            if not await _safe_goto(page, main_url):
                _log("사이트 접속 실패")
                return ProbeResult(
                    main_url=main_url,
                    final_url=main_url,
                    encoding="utf-8",
                    needs_login=False,
                    login_form_html="",
                    listing_html="",
                    detail_html="",
                    categories=[], sample_products=[],
                    login_url=login_url or "",
                )

            final_url = page.url
            _log(f"접속 완료: {final_url}")

            encoding = "utf-8"
            try:
                content = await page.content()
                if "euc-kr" in content.lower() or "euckr" in content.lower():
                    encoding = "euc-kr"
            except Exception:
                content = ""

            _log("로그인 폼 확인 중...")
            # If user provided login credentials, force needs_login = True
            needs_login = bool(login_url and username and password)
            login_form_html = ""
            if not needs_login:
                # Only check for password field on main page if user didn't provide login info
                try:
                    password_input = await page.query_selector("input[type='password']")
                    if password_input:
                        needs_login = True
                        form_html = await password_input.evaluate(
                            "el => el.closest('form') ? el.closest('form').outerHTML : ''"
                        )
                        login_form_html = reduce_html(form_html) if form_html else ""
                        _log("로그인 폼 발견됨")
                except Exception:
                    pass
            else:
                _log("로그인 정보 제공됨 (로그인 후 분석)")

            _log("카테고리 메뉴 확인 중...")
            category_menu_html = ""
            has_all_products = False
            try:
                all_link = await page.query_selector(
                    "a:has-text('전체'), a:has-text('ALL'), a:has-text('전체상품')"
                )
                if all_link:
                    has_all_products = True
                    _log("전체상품 메뉴 발견됨")
            except Exception:
                pass

            try:
                nav_selectors = [
                    "#MK_MENU_category_list",
                    ".category", ".nav-category", ".gnb", ".lnb",
                    "nav", ".menu", "#menu", ".navbar",
                    ".cate", "#cate",
                ]
                for sel in nav_selectors:
                    nav_el = await page.query_selector(sel)
                    if nav_el:
                        nav_html = await nav_el.inner_html()
                        category_menu_html = reduce_html(nav_html)
                        _log(f"카테고리 메뉴 발견: {sel}")
                        break
            except Exception:
                pass

            # Extract all categories directly via Playwright (no HTML reduction)
            categories: list[dict] = []
            try:
                cat_selectors = [
                    "#MK_MENU_category_list a[href*='shopbrand']",
                    "#MK_MENU_category_list a",
                    ".nav-category a[href*='shopbrand']",
                    ".nav-category a",
                    ".category a[href*='category']",
                    ".gnb a[href*='category']",
                    ".lnb a[href*='category']",
                    "nav a[href*='category']",
                    ".menu a[href*='shopbrand']",
                    "#cate a",
                    ".cate a",
                ]
                for cat_sel in cat_selectors:
                    cat_elements = await page.query_selector_all(cat_sel)
                    if cat_elements and len(cat_elements) > 2:
                        for el in cat_elements:
                            try:
                                name = (await el.inner_text()).strip()
                                href = await el.get_attribute("href")
                                if name and href:
                                    categories.append({"name": name, "url": href})
                            except Exception:
                                continue
                        if categories:
                            _log(f"카테고리 {len(categories)}개 발견 (Playwright 직접 추출)")
                            break
            except Exception:
                pass

            listing_url = sample_listing_url or final_url
            listing_html = ""

            if sample_listing_url and sample_listing_url != main_url:
                _log(f"상품 목록 페이지 접속 중: {sample_listing_url}")
                await _safe_goto(page, sample_listing_url)

            _log("상품 목록 분석 중...")
            try:
                listing_html = reduce_html(await page.content())
            except Exception:
                pass

            # Extract sample products with images and names via Playwright
            sample_products: list[dict] = []
            sample_links: list[str] = []
            try:
                product_patterns = [
                    "a[href*='shopdetail']",
                    "a[href*='goods']",
                    "a[href*='product']",
                    "a[href*='item']",
                    "a[href*='detail']",
                ]
                for pattern in product_patterns:
                    link_elements = await page.query_selector_all(pattern)
                    if link_elements and len(link_elements) > 0:
                        for link_el in link_elements[:15]:
                            try:
                                href = await link_el.get_attribute("href")
                                if not href:
                                    continue
                                
                                # Try to find an image near this link
                                image_url = None
                                name = ""
                                
                                # First try: img inside the link
                                try:
                                    img = await link_el.query_selector("img")
                                except Exception:
                                    img = None
                                
                                # Second try: img in the closest container (tr, div, li, td)
                                if not img:
                                    try:
                                        img = await link_el.evaluate(
                                            "el => { const container = el.closest('tr, div, li, td, dl'); "
                                            "return container ? container.querySelector('img') : null; }"
                                        )
                                        if img:
                                            # Can't use query_selector on evaluated result, get src via JS
                                            image_url = await link_el.evaluate(
                                                "el => { const container = el.closest('tr, div, li, td, dl'); "
                                                "const img = container ? container.querySelector('img') : null; "
                                                "return img ? (img.src || img.getAttribute('data-src') || '') : ''; }"
                                            )
                                    except Exception:
                                        pass
                                else:
                                    image_url = await img.get_attribute("src")
                                    if not image_url:
                                        image_url = await img.get_attribute("data-src")
                                    alt = await img.get_attribute("alt")
                                    if alt:
                                        name = alt
                                
                                # Get product name from link text or alt
                                if not name:
                                    try:
                                        name = (await link_el.inner_text()).strip()
                                    except Exception:
                                        name = ""
                                
                                # Clean up image URL
                                if image_url:
                                    image_url = image_url.strip()
                                    if image_url and not image_url.startswith("http"):
                                        image_url = urljoin(main_url, image_url)
                                
                                full_href = urljoin(main_url, href)
                                sample_links.append(full_href)
                                sample_products.append({
                                    "url": full_href,
                                    "image_url": image_url or "",
                                    "name": name or "(이름 없음)",
                                })
                            except Exception:
                                continue
                        if sample_products:
                            _log(f"상품 {len(sample_products)}개 발견 (이미지+이름 포함)")
                            break
            except Exception:
                pass

            # Extract total product count and page info
            total_product_count: int | None = None
            products_per_page: int | None = None
            total_pages: int | None = None

            try:
                import re as _re
                # Try to find "총 N개" pattern in page text
                page_text = await page.inner_text("body")
                count_match = _re.search(r"총\s*(\d+)\s*개", page_text)
                if count_match:
                    total_product_count = int(count_match.group(1))
                    _log(f"총 상품 수: {total_product_count}개")

                # Count products on current page
                if sample_products:
                    products_per_page = len(sample_products)

                # Find max page number from pagination links
                page_links = await page.query_selector_all("a[href*='page=']")
                max_page = 0
                for link in page_links:
                    try:
                        text = (await link.inner_text()).strip()
                        # Extract number from text like [2], [10], etc.
                        num_match = _re.search(r"\[?(\d+)\]?", text)
                        if num_match:
                            num = int(num_match.group(1))
                            if num > max_page:
                                max_page = num
                    except Exception:
                        continue
                if max_page > 0:
                    total_pages = max_page
                    _log(f"총 페이지 수: {total_pages}페이지")
            except Exception:
                pass

            detail_html = ""
            status_indicators: dict = {}
            sample_products, sample_links = normalize_sample_products(main_url, sample_products, sample_links)

            detail_url = sample_detail_url or (sample_links[0] if sample_links else None)
            if detail_url:
                full_url = urljoin(main_url, detail_url) if not detail_url.startswith("http") else detail_url
                _log(f"상품 상세 페이지 접속 중: {full_url}")
                if await _safe_goto(page, full_url):
                    try:
                        detail_html = reduce_html(await page.content())
                        # Extract status indicators from detail page
                        status_indicators: dict = {}
                        try:
                            # Check for soldout images
                            soldout_imgs = await page.query_selector_all("img[src*='soldout'], img[src*='sold_out'], img[alt*='품절'], img[alt*='soldout']")
                            status_indicators["has_soldout_image"] = len(soldout_imgs) > 0

                            # Check for cart/buy buttons (indicates product is available)
                            cart_imgs = await page.query_selector_all("img[src*='cart'], img[src*='buy'], img[src*='order'], img[src*='purchase']")
                            status_indicators["has_cart_button"] = len(cart_imgs) > 0

                            # Check for explicit status text
                            status_texts = await page.query_selector_all(":text('품절'), :text('판매중'), :text('soldout'), :text('완판')")
                            status_indicators["has_explicit_status"] = len(status_texts) > 0

                            # Check maxq hidden input (maxq=0 means sold out)
                            maxq_input = await page.query_selector("input[name='maxq']")
                            if maxq_input:
                                maxq_value = await maxq_input.get_attribute("value")
                                status_indicators["maxq_value"] = maxq_value or ""
                            else:
                                status_indicators["maxq_value"] = ""

                            _log(f"판매 상태 지표: cart={'있음' if status_indicators.get('has_cart_button') else '없음'}, "
                                 f"soldout_img={'있음' if status_indicators.get('has_soldout_image') else '없음'}, "
                                 f"maxq={status_indicators.get('maxq_value', '?')}")
                        except Exception as exc:
                            _log(f"판매 상태 지표 추출 실패: {exc}")
                            status_indicators = {}
                        _log("상품 상세 페이지 분석 완료")
                    except Exception:
                        _log("상품 상세 페이지 분석 실패")

            await page.close()

            _log("분석 완료")
            return ProbeResult(
                main_url=main_url,
                final_url=final_url,
                encoding=encoding,
                needs_login=needs_login,
                login_form_html=login_form_html,
                listing_html=listing_html,
                detail_html=detail_html,
                sample_links=sample_links[:15],
                ajax_requests=requests_log[:20],
                category_menu_html=category_menu_html,
                has_all_products=has_all_products,
                categories=categories,
                sample_products=sample_products,
                login_url=login_url or "",
                storage_state=storage_state,
                total_product_count=total_product_count,
                products_per_page=products_per_page,
                total_pages=total_pages,
                status_indicators=status_indicators,
            )

    return await asyncio.wait_for(_do_probe(), timeout=60)
