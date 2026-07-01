from __future__ import annotations

from typing import Callable

ProgressCallback = Callable[[str], None]


async def _safe_goto(page, url: str, wait_until: str = "domcontentloaded") -> bool:
    """Safely navigate to a URL with fallback."""
    try:
        await page.goto(url, wait_until=wait_until, timeout=15_000)
        await page.wait_for_timeout(1500)
        return True
    except Exception:
        try:
            await page.goto(url, wait_until="commit", timeout=10_000)
            await page.wait_for_timeout(2000)
            return True
        except Exception:
            return False


MODAL_TRIGGER_SELECTORS = [
    "button:has-text('로그인')",
    "a:has-text('로그인')",
    "button:has-text('LOGIN')",
    "a:has-text('LOGIN')",
    "button:has-text('Log in')",
    "a:has-text('Log in')",
    "button:has-text('Sign in')",
    "a:has-text('Sign in')",
    "button:has-text('로그인하기')",
    "a:has-text('로그인하기')",
    "[data-modal*='login']",
    "[data-bs-toggle='modal']",
    "[data-toggle='modal']",
    "[aria-haspopup='dialog']",
    "[data-bs-target*='login']",
    "[data-target*='login']",
]


async def _open_login_modal(page, _log=None) -> bool:
    """password 필드가 invisible일 때 모달 트리거 클릭 시도.
    
    Returns True if a trigger was clicked (modal may now be open).
    """
    for sel in MODAL_TRIGGER_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el:
                visible = await el.is_visible()
                if visible:
                    await el.click()
                    await page.wait_for_timeout(800)
                    if _log:
                        _log(f"로그인 모달 트리거 클릭: {sel}")
                    return True
        except Exception:
            continue
    return False


async def _ensure_password_visible(page, _log=None) -> bool:
    """password 필드가 visible해질 때까지 모달 트리거 시도.

    Note: 메인 프레임만 처리. iframe 내 모달은 caller가 별도 처리.

    Returns True if password field is visible (or became visible).
    """
    try:
        pw = await page.query_selector("input[type='password']")
        if pw and await pw.is_visible():
            return True
    except Exception:
        pass
    # Try opening modal
    for _ in range(3):
        if await _open_login_modal(page, _log):
            try:
                await page.wait_for_selector("input[type='password']", state="visible", timeout=3000)
                return True
            except Exception:
                continue
        else:
            break
    return False


async def perform_login(
    page,
    login_url: str,
    username: str,
    password: str,
    login_config: dict[str, str] | None = None,
    on_progress: ProgressCallback | None = None,
) -> bool:
    """Perform login with robust form-based heuristics.

    If login_config provides explicit selectors (id_selector, password_selector,
    submit_selector), those are used first.  Otherwise the probe's form-based
    approach is used: find input[type='password'] → find containing <form> →
    find id input in the same form → fill → submit → wait for navigation.

    Returns True when login appeared successful, False otherwise.
    """
    def _log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    _log(f"로그인 페이지로 이동: {login_url}")
    if not await _safe_goto(page, login_url):
        _log("로그인 페이지 접속 실패")
        return False

    # If login_config provides any explicit selectors, use selector-based approach
    if login_config and (
        login_config.get("id_selector")
        or login_config.get("password_selector")
        or login_config.get("submit_selector")
    ):
        return await _login_via_selectors(page, username, password, login_config, _log)

    # Otherwise, use the robust form-based approach
    return await _login_via_form_heuristics(page, username, password, _log)


async def _login_via_selectors(page, username: str, password: str, login_config: dict, _log) -> bool:
    """Login using explicit selectors resolved from login_config."""
    from app.analyzer.element_picker import resolve_login_selectors

    selectors = resolve_login_selectors(login_config)

    _log("로그인 입력 필드 탐색 중...")

    # 모달 로그인 처리: password 필드가 invisible이면 모달 트리거 클릭
    await _ensure_password_visible(page, _log)

    # Fill username
    username_filled = False
    for sel in selectors["id_candidates"]:
        try:
            el = await page.wait_for_selector(sel, state="visible", timeout=5000)
            if el:
                await el.fill(username)
                username_filled = True
                break
        except Exception:
            continue

    if not username_filled:
        _log("아이디 입력 필드를 찾을 수 없습니다")
        return False

    # Fill password
    password_filled = False
    for sel in selectors["password_candidates"]:
        try:
            el = await page.wait_for_selector(sel, state="visible", timeout=5000)
            if el:
                await el.fill(password)
                password_filled = True
                break
        except Exception:
            continue

    if not password_filled:
        _log("비밀번호 입력 필드를 찾을 수 없습니다")
        return False

    _log("로그인 정보 입력 중...")

    # Click submit
    _log("로그인 제출 중...")
    submitted = await _try_submit_selectors(page, selectors["submit_candidates"])

    if not submitted:
        _log("로그인 버튼을 찾을 수 없습니다")
        return False

    # Wait for navigation
    await page.wait_for_timeout(3000)
    _log("로그인 처리 대기 중...")

    if await _login_succeeded(page, login_config):
        _log("로그인 성공")
        return True
    _log("로그인에 실패했습니다. 로그인 URL과 계정 정보를 확인하세요.")
    return False


async def _find_login_inputs_async(page):
    """Find (id_input, password_input) on the main page or any child frame.

    Returns (id_element, password_element) or (None, None).
    """
    # Try main page first
    password_input = await page.query_selector("input[type='password']")
    if password_input is not None:
        form = await password_input.evaluate("el => el.closest('form')")
        if form:
            id_input = await page.query_selector(
                "form input[type='text'], form input[type='email'], "
                "form input[name*='id'], form input[name*='user'], form input[name*='member']"
            )
        else:
            id_input = await page.query_selector("input[type='text'], input[type='email']")
        return id_input, password_input

    # Search child frames (e.g. MakeShop login forms inside iframes).
    # Retry briefly because the iframe may not be ready immediately after navigation.
    for _ in range(6):
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                pw = await frame.query_selector("input[type='password']")
                if pw is not None:
                    form = await pw.evaluate("el => el.closest('form')")
                    if form:
                        id_input = await frame.query_selector(
                            "form input[type='text'], form input[type='email'], "
                            "form input[name*='id'], form input[name*='user'], form input[name*='member']"
                        )
                    else:
                        id_input = await frame.query_selector("input[type='text'], input[type='email']")
                    return id_input, pw
            except Exception:
                continue
        # No password field in any frame yet — wait and retry
        await page.wait_for_timeout(500)
    return None, None


async def _login_via_form_heuristics(page, username: str, password: str, _log) -> bool:
    """Robust form-based login: find password input (incl. iframes), find form, find id input."""
    _log("로그인 입력 필드 탐색 중...")
    # 모달/hidden 로그인 처리: password 필드가 invisible이면 모달 트리거 클릭
    await _ensure_password_visible(page, _log)
    id_input, password_input = await _find_login_inputs_async(page)
    if not password_input:
        _log("로그인 폼을 찾을 수 없습니다")
        return False
    if not id_input:
        _log("아이디 입력 필드를 찾을 수 없습니다")
        return False

    _log("로그인 정보 입력 중...")
    try:
        await id_input.fill(username)
    except Exception as exc:
        _log(f"아이디 입력 실패: {exc}")
        return False
    try:
        await password_input.fill(password)
    except Exception as exc:
        _log(f"비밀번호 입력 실패: {exc}")
        return False

    # Find and click submit button (includes MakeShop javascript:check() patterns)
    _log("로그인 제출 중...")
    submit_selectors = [
        "form button[type='submit']",
        "form input[type='submit']",
        "form input[type='image']",
        "form button:has-text('로그인')",
        "form a:has-text('로그인')",
        "form img[src*='login']",
        "form a[href*='javascript:check']",
        "form a[href*='check()']",
        "a[href*='javascript:check']",
        "a[href*='check()']",
        "a:has(img[src*='login'])",
        "button[type='submit']",
        "input[type='submit']",
        "input[type='image']",
    ]

    submitted = await _try_submit_selectors(page, submit_selectors)

    if not submitted:
        # MakeShop fallback: call check() directly in the frame holding the form.
        try:
            frame = password_input.owner_frame()
            if frame is not None:
                await frame.evaluate("typeof check === 'function' ? check() : undefined")
                submitted = True
        except Exception:
            pass

    if not submitted:
        # Try pressing Enter in the password field
        try:
            await password_input.press("Enter")
            submitted = True
        except Exception:
            pass

    if not submitted:
        _log("로그인 버튼을 찾을 수 없습니다")
        return False

    # Wait for navigation
    await page.wait_for_timeout(3000)
    _log("로그인 처리 대기 중...")

    if await _login_succeeded(page):
        _log("로그인 성공")
        return True

    _log("로그인에 실패했습니다. 로그인 URL과 계정 정보를 확인하세요.")
    return False


async def _try_submit_selectors(page, selectors: list[str]) -> bool:
    for sel in selectors:
        try:
            btn = await page.query_selector(sel)
            if btn:
                await btn.click()
                return True
        except Exception:
            continue
    return False


async def _check_logout_indicators(page) -> bool:
    """Check if login succeeded by looking for logout indicators."""
    logout_indicators = [
        "a[href*='logout']",
        "img[src*='logout']",
        "a:has-text('로그아웃')",
        "a:has-text('LOGOUT')",
    ]
    try:
        for sel in logout_indicators:
            el = await page.query_selector(sel)
            if el:
                return True
    except Exception:
        pass
    return False


async def _has_visible_password_input(page) -> bool:
    try:
        pw = await page.query_selector("input[type='password']")
        if pw and await pw.is_visible():
            return True
    except Exception:
        pass
    for frame in getattr(page, "frames", []):
        if frame == getattr(page, "main_frame", None):
            continue
        try:
            pw = await frame.query_selector("input[type='password']")
            if pw and await pw.is_visible():
                return True
        except Exception:
            continue
    return False


async def _login_succeeded(page, login_config: dict[str, str] | None = None) -> bool:
    cfg = login_config or {}
    failure_indicator = cfg.get("failure_indicator") or ""
    if failure_indicator:
        try:
            failed = await page.query_selector(failure_indicator)
            if failed:
                return False
        except Exception:
            pass

    success_indicator = cfg.get("success_indicator") or ""
    if success_indicator:
        try:
            return await page.query_selector(success_indicator) is not None
        except Exception:
            return False

    if await _check_logout_indicators(page):
        return True
    return not await _has_visible_password_input(page)
