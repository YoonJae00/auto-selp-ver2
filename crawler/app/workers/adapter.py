from __future__ import annotations

import asyncio
import json
import os
import queue
import re
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine
from urllib.parse import urljoin

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.analyzer.adapter_generator import generate_adapter_yaml, repair_adapter_fields
from app.analyzer.adapter_schema import clean_field_value, extract_url_value
from app.analyzer.option_text_parser import is_option_placeholder, parse_option_text, format_option_group
from app.analyzer.picker_session import PickerSession
from app.analyzer.site_probe import probe_site
from app.crawlers.yaml_adapter import (
    _image_key,
    _status_from_maxq_value,
    collect_detail_images,
    option_is_soldout,
    status_from_cart_button,
    SOLDOUT_MARKER_SELECTOR,
    CART_BUTTON_SELECTOR,
)


@dataclass
class ProbeRequest:
    main_url: str
    listing_url: str | None = None
    detail_url: str | None = None
    login_url: str | None = None
    username: str | None = None
    password: str | None = None


@dataclass
class GenerateRequest:
    probe_result: Any
    supplier_name: str
    provider: str = "gemini"
    auto_fallback: bool = True
    mapping_hints: list[Any] = field(default_factory=list)


@dataclass
class AdapterRepairRequest:
    yaml_text: str
    failed_fields: list[str]
    probe_result: Any
    provider: str = "gemini"
    auto_fallback: bool = True


@dataclass
class PickerRequest:
    field_path: str
    target_url: str
    login_url: str | None = None
    username: str | None = None
    password: str | None = None
    login_config: dict[str, str] | None = None
    field_label: str = ""
    field_hint: str = ""
    storage_state: dict | None = None
    supplier_key: str | None = None


@dataclass
class CategoryMenuProbeRequest:
    url: str
    selector: str
    selector_candidates: list[str] = field(default_factory=list)
    storage_state: dict | None = None
    supplier_key: str | None = None


@dataclass
class AdapterTestRequest:
    adapter_yaml: str
    test_urls: list[str]
    tested_yaml_hash: str
    login_url: str | None = None
    username: str | None = None
    password: str | None = None
    fields: tuple[str, ...] | None = None
    storage_state: dict | None = None
    supplier_key: str | None = None


@dataclass
class MappingPreviewRequest:
    yaml_text: str
    target_url: str
    fields: list[dict]
    login_url: str | None = None
    username: str | None = None
    password: str | None = None
    storage_state: dict | None = None
    supplier_key: str | None = None


@dataclass
class OptionTextParserAnalyzeRequest:
    yaml_text: str
    target_url: str
    login_url: str | None = None
    username: str | None = None
    password: str | None = None
    storage_state: dict | None = None
    supplier_key: str | None = None


@dataclass
class SoldoutCompareRequest:
    adapter_yaml: str
    available_url: str
    soldout_url: str
    login_url: str | None = None
    username: str | None = None
    password: str | None = None
    storage_state: dict | None = None
    supplier_key: str | None = None


@dataclass
class AutoAdapterRequest:
    main_url: str
    supplier_name: str
    listing_url: str | None = None
    detail_url: str | None = None
    login_url: str | None = None
    username: str | None = None
    password: str | None = None
    provider: str = "gemini"
    auto_fallback: bool = True
    supplier_key: str | None = None
    soldout_url: str | None = None  # 사용자가 직접 입력한 품절 상품 URL (UI 뷰모델 계약)
    option_url: str | None = None   # 옵션 있는 상품 URL — 옵션 evidence/검증을 이 페이지 기준으로 (UI 뷰모델 계약)


class _AsyncWorker(QThread):
    error = Signal(str)
    progress = Signal(str)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None

    def requestInterruption(self) -> None:
        super().requestInterruption()
        loop, task = self._loop, self._task
        if loop is not None and task is not None and loop.is_running():
            loop.call_soon_threadsafe(task.cancel)

    def _run_async(self, coroutine: Coroutine[Any, Any, Any], emit_result) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            asyncio.set_event_loop(loop)
            task = loop.create_task(coroutine)
            self._task = task
            if self.isInterruptionRequested():
                task.cancel()
            result = loop.run_until_complete(task)
            if not self.isInterruptionRequested():
                emit_result(result)
            else:
                self.cancelled.emit()
        except asyncio.CancelledError:
            self.cancelled.emit()
        except Exception as exc:
            if self.isInterruptionRequested():
                self.cancelled.emit()
            else:
                self.error.emit(str(exc))
        finally:
            self._task = None
            self._loop = None
            asyncio.set_event_loop(None)
            loop.close()


class _PickerThread(QThread):
    """Long-lived thread owning the PickerSession.

    Playwright's sync API is thread-affine (greenlet binds to the creating
    thread), so the browser session must live on a single stable thread for
    its whole lifetime. This thread stays alive across many pick requests;
    each request is handled by a ``PickerJob`` relay object that exposes the
    same interface the view-model expects from a worker.
    """

    def __init__(self) -> None:
        super().__init__()
        self._queue: "queue.Queue[Any]" = queue.Queue()
        self._session: PickerSession | None = None
        self._current_job: "PickerJob | None" = None
        self._lock = threading.Lock()

    def submit(self, job: "PickerJob") -> None:
        self._queue.put(job)

    def close_session(self) -> None:
        """Ask the thread to close the browser but keep running for later picks."""
        self._queue.put(_CLOSE_SESSION)

    def interrupt_current(self) -> None:
        """Best-effort unblock of an in-flight pick (closes the live page)."""
        with self._lock:
            session = self._session
        if session is None:
            return
        page = getattr(session, "_page", None)
        if page is not None:
            try:
                if not page.is_closed():
                    page.close()
            except Exception:
                pass

    def run(self) -> None:
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                if item is _CLOSE_SESSION:
                    if self._session is not None:
                        try:
                            self._session.close()
                        except Exception:
                            pass
                        self._session = None
                    continue
                job = item
                with self._lock:
                    self._current_job = job
                try:
                    job._execute(self)
                finally:
                    with self._lock:
                        self._current_job = None
        finally:
            if self._session is not None:
                try:
                    self._session.close()
                except Exception:
                    pass
                self._session = None


_CLOSE_SESSION = object()


def _is_picker_cancel_or_close(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "cancelled" in message
        or "has been closed" in message
        or "target page" in message
        or "browser has been closed" in message
        or ("context" in message and "closed" in message)
    )


def _discard_picker_session(thread: _PickerThread, session: PickerSession | None) -> None:
    try:
        if session is not None:
            session.close()
    except Exception:
        pass
    thread._session = None


_picker_thread: _PickerThread | None = None
_picker_thread_lock = threading.Lock()


def _ensure_picker_thread() -> _PickerThread:
    global _picker_thread
    with _picker_thread_lock:
        if _picker_thread is None or not _picker_thread.isRunning():
            _picker_thread = _PickerThread()
            _picker_thread.start()
        return _picker_thread


def stop_picker_thread() -> None:
    """Stop the long-lived picker thread (used on application shutdown)."""
    global _picker_thread
    with _picker_thread_lock:
        thread = _picker_thread
        _picker_thread = None
    if thread is None:
        return
    thread.interrupt_current()
    thread._queue.put(None)
    if thread.isRunning():
        thread.wait(2000)


class PickerJob(QObject):
    """Per-request relay object that mimics the QThread worker interface.

    The view-model connects to ``finished``/``error``/``progress``/``cancelled``
    and calls ``start``/``requestInterruption``/``isRunning``/``wait`` exactly
    as it would for a ``QThread`` worker. The actual work runs on the shared
    ``_PickerThread`` so the Playwright session never crosses threads (which
    would raise ``greenlet.error: cannot switch to a different thread``).
    """

    finished = Signal(object, str)
    error = Signal(str)
    progress = Signal(str)
    cancelled = Signal()
    login_required = Signal()

    def __init__(self, request: PickerRequest) -> None:
        super().__init__()
        self.request = request
        self._interrupted = False
        self._done = threading.Event()
        self._manual_login_event = threading.Event()
        self._manual_login_cancelled = False
        self._thread: _PickerThread | None = None

    def start(self) -> None:
        self._thread = _ensure_picker_thread()
        self._thread.submit(self)

    def requestInterruption(self) -> None:
        self._interrupted = True
        if self._thread is not None:
            self._thread.interrupt_current()

    @Slot()
    def confirmManualLogin(self) -> None:
        """User confirmed they logged in manually in the browser — resume pick."""
        self._manual_login_event.set()

    @Slot()
    def cancelManualLogin(self) -> None:
        """User cancelled the manual-login prompt — abort the pick."""
        self._manual_login_cancelled = True
        self._manual_login_event.set()

    def _analyze_login_with_llm(self, session) -> dict[str, str] | None:
        """Use LLM to analyze the login page HTML and extract form selectors."""
        import asyncio
        import json
        from app.analyzer.llm_client import QuotaExceededError, get_llm_client
        from app.config import load_config

        html = session.get_login_page_html()
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

        response = asyncio.run(client.generate(system_prompt, user_prompt))

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

    def isRunning(self) -> bool:
        return not self._done.is_set()

    def wait(self, timeout_ms: int = 0) -> bool:
        if timeout_ms <= 0:
            self._done.wait()
            return True
        return self._done.wait(timeout_ms / 1000.0)

    def terminate(self) -> None:
        self.requestInterruption()

    def _execute(self, thread: _PickerThread) -> None:
        session: PickerSession | None = None
        try:
            session = thread._session
            if session is None or not session.is_open:
                # storage_state 준비: request에서 직접 또는 session_store에서 로드
                state = self.request.storage_state
                if state is None and self.request.supplier_key:
                    try:
                        from app.analyzer.session_store import load_session_state
                        state = load_session_state(self.request.supplier_key)
                    except Exception:
                        pass
                session = PickerSession(headless=False)
                session.open(storage_state=state)
                thread._session = session
                # storage_state가 있으면 target URL 열어 인증 검증 (재로그인 스킵 목적)
                if state and not session.is_logged_in:
                    try:
                        self.progress.emit(f"세션 확인 중: {self.request.target_url}")
                        page = session._ensure_page()
                        page.goto(self.request.target_url, wait_until="domcontentloaded", timeout=20_000)
                        page.wait_for_timeout(1500)
                        if session._verify_logged_in(page):
                            session._logged_in = True
                            session._current_url = self.request.target_url
                            self.progress.emit("기존 세션으로 인증 확인됨")
                    except Exception:
                        pass
            if (
                self.request.login_url
                and self.request.username
                and self.request.password
                and not session.is_logged_in
            ):
                self.progress.emit("로그인 중...")
                login_ok = False
                try:
                    login_ok = session.login(
                        self.request.login_url,
                        self.request.username,
                        self.request.password,
                        self.request.login_config,
                    )
                except Exception as exc:
                    self.progress.emit(f"1차 로그인 시도 실패: {exc}")
                    login_ok = False
                if login_ok and self.request.supplier_key:
                    try:
                        from app.analyzer.session_store import save_session_state
                        state = session.get_storage_state()
                        if state:
                            save_session_state(self.request.supplier_key, state)
                    except Exception:
                        pass
                if not login_ok and not self._interrupted:
                    # Auto-login failed: try LLM-assisted analysis before manual fallback.
                    self.progress.emit("AI가 로그인 페이지 분석 중...")
                    try:
                        llm_login_config = self._analyze_login_with_llm(session)
                        if llm_login_config:
                            self.progress.emit("AI 분석 완료 — 추출된 선택자로 재시도 중...")
                            try:
                                login_ok = session.login(
                                    self.request.login_url,
                                    self.request.username,
                                    self.request.password,
                                    llm_login_config,
                                )
                            except Exception as exc:
                                self.progress.emit(f"AI 선택자 로그인 실패: {exc}")
                                login_ok = False
                    except Exception as exc:
                        self.progress.emit(f"AI 분석 실패: 수동 로그인으로 전환합니다.")

                if not login_ok and not self._interrupted:
                    # LLM analysis also failed (or wasn't possible): manual login fallback.
                    self.progress.emit("자동 로그인 실패 — 브라우저에서 직접 로그인해주세요.")
                    self.login_required.emit()
                    self._manual_login_event.wait(timeout=300)  # 5-minute timeout
                    if self._manual_login_cancelled or self._interrupted:
                        if not self._interrupted:
                            self.cancelled.emit()
                        return
                    # User confirmed manual login — treat session as authenticated
                    session._logged_in = True
                    try:
                        page = session._ensure_page()
                        if session._verify_logged_in(page) and self.request.supplier_key:
                            from app.analyzer.session_store import save_session_state
                            s = session.get_storage_state()
                            if s:
                                save_session_state(self.request.supplier_key, s)
                    except Exception:
                        pass
            self.progress.emit(f"페이지 이동: {self.request.target_url}")
            try:
                result = session.pick(
                    self.request.target_url,
                    self.request.field_label,
                    self.request.field_hint,
                    field_path=self.request.field_path,
                )
                if self.request.field_path == "adapter.categories.navigation.menu_selector":
                    # Extract category links from the already-rendered visible browser.
                    # Avoids launching a headless browser that may miss JS-rendered menus.
                    try:
                        page = session._ensure_page()
                        links = page.evaluate(
                            r"""
                            (selector) => {
                              function findContainer(el) {
                                let node = el.parentElement;
                                for (let i = 0; i < 10 && node && node !== document.body; i++) {
                                  if (node.querySelectorAll('a[href]').length >= 2) return node;
                                  node = node.parentElement;
                                }
                                return el.parentElement || el;
                              }
                              const out = [], seen = new Set();
                              for (const el of Array.from(document.querySelectorAll(selector)).slice(0, 5)) {
                                for (const a of findContainer(el).querySelectorAll('a[href]')) {
                                  const name = (a.innerText||a.textContent||'').replace(/\s+/g,' ').trim();
                                  const rawHref = a.getAttribute('href')||'';
                                  if (!name||!rawHref||rawHref==='#'||/^javascript:|^mailto:|^tel:/i.test(rawHref)) continue;
                                  try {
                                    const url = new URL(rawHref, location.href).href;
                                    const key = name+'\n'+url;
                                    if (seen.has(key)) continue;
                                    seen.add(key); out.push({name, url});
                                    if (out.length >= 50) return out;
                                  } catch(_) {}
                                }
                              }
                              return out;
                            }
                            """,
                            result.selector,
                        )
                        result.container_links = [
                            {"name": str(lnk.get("name", "")), "url": str(lnk.get("url", ""))}
                            for lnk in (links or [])
                            if lnk.get("name") and lnk.get("url")
                        ]
                    except Exception as _link_exc:
                        pass
                    try:
                        session.close()
                    finally:
                        thread._session = None
                if not self._interrupted:
                    self.finished.emit(result, self.request.field_path)
            except RuntimeError as exc:
                if not self._interrupted:
                    if _is_picker_cancel_or_close(exc):
                        _discard_picker_session(thread, session)
                        self.cancelled.emit()
                    else:
                        self.error.emit(str(exc))
        except Exception as exc:
            if not self._interrupted:
                if _is_picker_cancel_or_close(exc):
                    _discard_picker_session(thread, session)
                    self.cancelled.emit()
                else:
                    self.error.emit(str(exc))
        finally:
            self.request.password = None
            self._done.set()


# Backwards-compatible alias for any external reference to the old name.
PickerWorker = PickerJob


class MappingPreviewJob(QObject):
    """Non-blocking picker-thread job that opens a URL and injects mapping overlays."""

    finished = Signal(object)   # {"found": [...], "missing": [...]}
    error = Signal(str)
    progress = Signal(str)
    cancelled = Signal()

    def __init__(self, request: MappingPreviewRequest) -> None:
        super().__init__()
        self.request = request
        self._interrupted = False
        self._done = threading.Event()
        self._thread: _PickerThread | None = None

    def start(self) -> None:
        self._thread = _ensure_picker_thread()
        self._thread.submit(self)

    def requestInterruption(self) -> None:
        self._interrupted = True
        if self._thread is not None:
            self._thread.interrupt_current()

    def isRunning(self) -> bool:
        return not self._done.is_set()

    def wait(self, ms: int = 0) -> bool:
        return self._done.wait(ms / 1000 if ms else None)

    def _execute(self, thread: _PickerThread) -> None:
        session: PickerSession | None = None
        try:
            session = thread._session
            if session is None or not session.is_open:
                state = self.request.storage_state
                if state is None and self.request.supplier_key:
                    try:
                        from app.analyzer.session_store import load_session_state
                        state = load_session_state(self.request.supplier_key)
                    except Exception:
                        pass
                session = PickerSession(headless=False)
                session.open(storage_state=state)
                thread._session = session
                if state and not session.is_logged_in:
                    try:
                        self.progress.emit(f"세션 확인 중: {self.request.target_url}")
                        page = session._ensure_page()
                        page.goto(self.request.target_url, wait_until="domcontentloaded", timeout=20_000)
                        page.wait_for_timeout(1500)
                        if session._verify_logged_in(page):
                            session._logged_in = True
                            self.progress.emit("기존 세션으로 인증 확인됨")
                    except Exception:
                        pass
            if (
                self.request.login_url
                and self.request.username
                and self.request.password
                and not session.is_logged_in
            ):
                self.progress.emit("로그인 중...")
                try:
                    session.login(
                        self.request.login_url,
                        self.request.username,
                        self.request.password,
                    )
                except Exception as exc:
                    self.progress.emit(f"로그인 실패: {exc}")

            self.progress.emit(f"페이지 이동: {self.request.target_url}")
            result = session.preview_mapping(self.request.target_url, self.request.fields)
            if not self._interrupted:
                self.finished.emit(result)
        except Exception as exc:
            if not self._interrupted:
                if _is_picker_cancel_or_close(exc):
                    _discard_picker_session(thread, session)
                    self.cancelled.emit()
                else:
                    self.error.emit(str(exc))
        finally:
            self.request.password = None
            self._done.set()


def close_picker_session() -> None:
    """Close the persistent browser without stopping the picker thread."""
    with _picker_thread_lock:
        thread = _picker_thread
    if thread is not None and thread.isRunning():
        thread.interrupt_current()
        thread.close_session()


class ProbeWorker(_AsyncWorker):
    finished = Signal(object)
    def __init__(self, request: ProbeRequest) -> None:
        super().__init__()
        self.request = request

    def run(self) -> None:
        try:
            self._run_async(probe_site(
                self.request.main_url, self.request.listing_url,
                self.request.detail_url, headless=True, on_progress=self.progress.emit,
                login_url=self.request.login_url, username=self.request.username,
                password=self.request.password,
            ), self.finished.emit)
        finally:
            self.request.password = None


class GenerateWorker(_AsyncWorker):
    finished = Signal(str, str, int)
    def __init__(self, request: GenerateRequest) -> None:
        super().__init__()
        self.request = request

    def run(self) -> None:
        self._run_async(generate_adapter_yaml(
            self.request.probe_result, self.request.supplier_name,
            llm_provider=self.request.provider, auto_fallback=self.request.auto_fallback,
            on_progress=self.progress.emit, mapping_hints=self.request.mapping_hints,
        ), lambda result: self.finished.emit(result.yaml_text, result.provider_used, result.retries))


class AdapterRepairWorker(_AsyncWorker):
    finished = Signal(str)

    def __init__(self, request: AdapterRepairRequest) -> None:
        super().__init__()
        self.request = request

    def run(self) -> None:
        self._run_async(repair_adapter_fields(
            self.request.yaml_text, self.request.failed_fields, self.request.probe_result,
            llm_provider=self.request.provider, auto_fallback=self.request.auto_fallback,
            on_progress=self.progress.emit,
        ), self.finished.emit)


def _strip_json_response(response: str) -> str:
    text_resp = response.strip()
    if text_resp.startswith("```"):
        lines = text_resp.split("\n")
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text_resp = "\n".join(lines[1:end])
    return text_resp.strip()


def _button_signature(button: dict) -> str:
    """버튼 식별 시그니처. 같은 요소면 판매중/품절 페이지에서 동일해야 한다.

    이미지 버튼은 src 파일명(쿼리스트링 제거), 그 외에는 텍스트를 쓴다. 전역 네비/헤더처럼
    양쪽 페이지에 똑같이 있는 버튼은 시그니처가 같아 집합 차이에서 상쇄된다.
    """
    html = str(button.get("html") or "")
    m = re.search(r"src=[\"']([^\"']+)", html)
    if m:
        src = m.group(1).split("?", 1)[0]
        return "img:" + src.rsplit("/", 1)[-1].lower()
    text = str(button.get("text") or "").strip().lower()
    return "text:" + text if text else "html:" + html[:120]


def _button_selector(button: dict) -> str:
    """판별 버튼을 런타임에서 다시 찾기 위한 구체 셀렉터."""
    html = str(button.get("html") or "")
    m = re.search(r"src=[\"']([^\"']+)", html)
    if m:
        base = m.group(1).split("?", 1)[0].rsplit("/", 1)[-1]
        if base:
            return f"img[src*='{base}']"
    text = str(button.get("text") or "").strip()
    return f"button:has-text('{text}')" if text else ""


def _status_suggestion_from_snapshots(available: dict, soldout: dict) -> dict | None:
    available_maxq = str(available.get("maxq_value") or "").strip()
    soldout_maxq = str(soldout.get("maxq_value") or "").strip()
    if soldout_maxq == "0" and available_maxq and available_maxq != "0":
        return {
            "selector": "",
            "fallback_from": "maxq",
            "mapping": {"available": "available", "sold_out": "sold_out"},
            "default": "available",
            "confidence": "high",
            "note": "품절 상품의 maxq 값이 0이고 판매중 상품은 0이 아닙니다.",
        }
    # 불리언 유무가 아니라 버튼 집합 차이로 비교한다: 전역 네비/헤더처럼 양쪽에 공통인
    # 버튼은 상쇄되고, 판매중에만 있는 실제 상품 장바구니 버튼만 남는다.
    soldout_sigs = {_button_signature(b) for b in soldout.get("buy_buttons") or []}
    avail_only = [b for b in available.get("buy_buttons") or [] if _button_signature(b) not in soldout_sigs]
    if avail_only:
        # 가장 장바구니/구매다운 버튼을 판별자로 고른다.
        def _cartness(b: dict) -> int:
            blob = (str(b.get("html") or "") + str(b.get("text") or "")).lower()
            return sum(kw in blob for kw in ("cart", "buy", "구매", "장바구니", "purchase"))
        pick = max(avail_only, key=_cartness)
        selector = _button_selector(pick)
        return {
            "selector": selector,
            "fallback_from": "cart_button",
            "mapping": {"available": "available", "sold_out": "sold_out"},
            "default": "available",
            "confidence": "high" if selector else "medium",
            "note": "판매중 상품에만 있는 구매/장바구니 버튼을 발견했습니다.",
        }
    return None


class SoldoutCompareWorker(_AsyncWorker):
    finished = Signal(dict)

    def __init__(self, request: SoldoutCompareRequest) -> None:
        super().__init__()
        self.request = request

    def run(self) -> None:
        try:
            self._run_async(self._compare(), self.finished.emit)
        finally:
            self.request.password = None

    async def _compare(self) -> dict:
        from app.analyzer.html_reducer import reduce_html
        from app.analyzer.llm_client import get_llm_client
        from app.analyzer.login_helper import perform_login as _login_shared
        from app.config import load_config
        from app.crawlers.engine import create_engine
        from app.crawlers.registry import load_adapter_from_text

        load_adapter_from_text(self.request.adapter_yaml)
        state = self.request.storage_state
        if state is None and self.request.supplier_key:
            try:
                from app.analyzer.session_store import load_session_state
                state = load_session_state(self.request.supplier_key)
            except Exception:
                pass

        self.progress.emit("[progress:0.00] 판매중/품절 상품 비교 시작")
        async with create_engine(headless=True, storage_state=state) as engine:
            page = await engine.new_page()
            if self.request.login_url and self.request.username and self.request.password and state is None:
                self.progress.emit("로그인 중...")
                await _login_shared(
                    page,
                    self.request.login_url,
                    self.request.username,
                    self.request.password,
                    on_progress=self.progress.emit,
                )
            available = await self._snapshot(page, self.request.available_url, reduce_html)
            self.progress.emit("[progress:0.45] 판매중 상품 분석 완료")
            soldout = await self._snapshot(page, self.request.soldout_url, reduce_html)
            self.progress.emit("[progress:0.70] 품절 상품 분석 완료")
            await page.close()

        suggestion = _status_suggestion_from_snapshots(available, soldout)
        if suggestion:
            self.progress.emit("[progress:1.00] 판매 상태 비교 완료")
            return {**suggestion, "available_url": self.request.available_url, "soldout_url": self.request.soldout_url}

        config = load_config()
        provider = config.llm_provider
        client = get_llm_client(provider)
        system_prompt = (
            "당신은 쇼핑몰 상세 페이지에서 품절을 나타내는 DOM 요소를 찾는 전문가입니다. "
            "판매중 상품과 품절 상품의 축약 DOM과 상태 후보를 비교해 YAML 어댑터에 넣을 값을 JSON으로만 응답하세요.\n\n"
            "응답 형식:\n"
            '{"selector":"CSS선택자 또는 빈 문자열","fallback_from":"none|cart_button|maxq",'
            '"mapping":{"품절":"sold_out","판매중":"available"},"default":"available|unknown",'
            '"confidence":"high|medium|low","note":"간단한 설명"}\n\n'
            "규칙:\n"
            "1. 품절 상품에만 있는 텍스트/이미지/disabled 버튼 선택자가 있으면 selector를 제안하세요.\n"
            "2. 판매중에만 구매/장바구니 버튼이 있으면 fallback_from은 cart_button입니다.\n"
            "3. maxq가 품절 0, 판매중 0 아님이면 fallback_from은 maxq입니다.\n"
            "4. 확신이 없으면 confidence를 low로 주세요."
        )
        user_prompt = (
            f"판매중 URL: {self.request.available_url}\n"
            f"품절 URL: {self.request.soldout_url}\n\n"
            f"판매중 상태 후보:\n{json.dumps(available, ensure_ascii=False)[:8000]}\n\n"
            f"품절 상태 후보:\n{json.dumps(soldout, ensure_ascii=False)[:8000]}"
        )
        try:
            response = await client.generate(system_prompt, user_prompt)
        except QuotaExceededError:
            if not config.auto_fallback_enabled:
                raise
            provider = "openai" if provider == "gemini" else "gemini"
            self.progress.emit(f"할당량 초과, {provider}로 전환합니다...")
            response = await get_llm_client(provider).generate(system_prompt, user_prompt)
        try:
            raw = json.loads(_strip_json_response(response))
        except json.JSONDecodeError:
            raw = {"confidence": "low", "note": "AI 응답 파싱 실패"}
        result = self._normalize_result(raw)
        self.progress.emit("[progress:1.00] 판매 상태 비교 완료")
        return {**result, "available_url": self.request.available_url, "soldout_url": self.request.soldout_url}

    async def _snapshot(self, page, url: str, reduce_html) -> dict:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1200)
        html = ""
        try:
            html = reduce_html(await page.content())[:12000]
        except Exception:
            pass
        maxq_value = ""
        maxq = await page.query_selector("input[name='maxq']")
        if maxq:
            maxq_value = await maxq.get_attribute("value") or ""
        explicit = await self._collect_matches(page, SOLDOUT_MARKER_SELECTOR)
        buy_buttons = await self._collect_matches(page, CART_BUTTON_SELECTOR)
        disabled = await self._collect_matches(
            page,
            "button[disabled], input[disabled], .disabled, .soldout, .sold_out, [class*='soldout'], [class*='sold_out']",
        )
        return {
            "url": url,
            "maxq_value": maxq_value,
            "has_buy_button": bool(buy_buttons),
            "buy_buttons": buy_buttons[:8],
            "explicit_soldout": explicit[:8],
            "disabled_candidates": disabled[:8],
            "html": html,
        }

    async def _collect_matches(self, page, selector: str) -> list[dict[str, str]]:
        try:
            elements = await page.query_selector_all(selector)
        except Exception:
            return []
        rows: list[dict[str, str]] = []
        for el in elements[:12]:
            try:
                rows.append({
                    "text": (await el.inner_text() or "").strip()[:120],
                    "html": (await el.evaluate("el => el.outerHTML") or "")[:400],
                })
            except Exception:
                continue
        return rows

    def _normalize_result(self, raw: dict) -> dict:
        selector = str(raw.get("selector") or "").strip()
        fallback_from = str(raw.get("fallback_from") or "none").strip()
        if fallback_from not in {"none", "cart_button", "maxq"}:
            fallback_from = "none"
        confidence = str(raw.get("confidence") or "low").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"
        mapping = raw.get("mapping")
        if not isinstance(mapping, dict):
            mapping = {}
        default = str(raw.get("default") or "available").strip()
        if default not in {"available", "unknown", "sold_out", "stopped"}:
            default = "available"
        if not selector and fallback_from == "none":
            confidence = "low"
        return {
            "selector": selector,
            "fallback_from": fallback_from,
            "mapping": {str(k): str(v) for k, v in mapping.items()},
            "default": default,
            "confidence": confidence,
            "note": str(raw.get("note") or "").strip()[:200],
        }


class AdapterTestWorker(_AsyncWorker):
    finished = Signal(dict)
    IMAGE_PREVIEW_FIELDS = {"detail_content", "extra_image_urls"}
    FIELD_NAMES = (
        "supplier_product_code", "raw_product_name",
        "supplier_status", "supply_price", "origin", "main_image_url",
        "detail_content", "extra_image_urls", "option_values",
    )

    def __init__(
        self,
        request: AdapterTestRequest,
        screenshot_dir: str | None = None,
        on_screenshot: Callable[[str, str], None] | None = None,  # (url, path)
    ) -> None:
        super().__init__()
        self.request = request
        self.adapter_yaml = request.adapter_yaml
        self.test_urls = list(request.test_urls)
        self.tested_yaml_hash = request.tested_yaml_hash
        self.login_url = request.login_url
        self.username = request.username
        self.password = request.password
        self.fields = tuple(request.fields or self.FIELD_NAMES)
        self.storage_state = request.storage_state
        self.supplier_key = request.supplier_key
        self.screenshot_dir = screenshot_dir  # None(기본) = 수동 마법사 경로 무변경
        self.on_screenshot = on_screenshot
        self.raw_results: dict[str, list[dict]] = {}
        self._shot_seq = 0

    def run(self) -> None:
        try:
            self._run_async(self._run_test(), self.finished.emit)
        finally:
            self.password = None
            self.request.password = None

    async def _run_test(self) -> dict:
        from app.crawlers.engine import create_engine
        from app.crawlers.registry import load_adapter_from_text

        adapter = load_adapter_from_text(self.adapter_yaml)
        # 옵션은 선택사항: 옵션 그룹이 없는데 전체 테스트(fields 미지정)면 option_values를
        # 실패 행으로 만들지 않도록 제외한다. 사용자가 명시 요청한 경우(request.fields)는 그대로.
        if self.request.fields is None and not adapter.adapter.options.groups:
            self.fields = tuple(f for f in self.fields if f not in ("option_values", "option_prices"))
        aggregate: dict[str, list[dict]] = {name: [] for name in self.fields}
        total_fields = len(self.test_urls) * len(self.fields)
        completed_fields = 0
        self.progress.emit(
            f"[progress:0.00] 테스트 시작: {len(self.test_urls)}개 URL × {len(self.fields)}개 필드"
        )
        # storage_state 준비: request에서 직접 또는 session_store에서 로드
        state = self.storage_state
        if state is None and self.supplier_key:
            try:
                from app.analyzer.session_store import load_session_state
                state = load_session_state(self.supplier_key)
            except Exception:
                pass
        async with create_engine(headless=True, storage_state=state) as engine:
            page = await engine.new_page()
            # storage_state가 있으면 로그인 생략 가능 (이미 인증됨)
            if self.login_url and self.username and self.password and state is None:
                await self._login(page)
            product = adapter.adapter.product
            for url in self.test_urls:
                self.progress.emit(f"테스트 페이지 접속: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1500)
                if self.screenshot_dir:
                    # best-effort — 스크린샷 실패가 테스트를 막지 않는다.
                    try:
                        self._shot_seq += 1
                        shot_path = os.path.join(self.screenshot_dir, f"shot_{self._shot_seq}.png")
                        await page.screenshot(path=shot_path)
                        if self.on_screenshot:
                            self.on_screenshot(url, shot_path)
                    except Exception:
                        pass
                main_image_url: str | None = None
                for field_name in self.fields:
                    fraction = completed_fields / total_fields if total_fields else 0.0
                    extractor = getattr(product, field_name, None)
                    value = error = image_urls = None
                    if field_name in {"option_values", "option_prices"}:
                        self.progress.emit(f"[progress:{fraction:.2f}] 테스트 중: {field_name}")
                        try:
                            value = await self._extract_test_option(page, adapter, field_name)
                        except Exception as exc:
                            error = str(exc)
                    elif extractor:
                        self.progress.emit(f"[progress:{fraction:.2f}] 테스트 중: {field_name}")
                        try:
                            value, image_urls = await self._extract_test_field(page, extractor, field_name)
                            if field_name == "main_image_url" and value:
                                main_image_url = urljoin(url, value)
                            # 추가이미지/상세이미지에 대표이미지가 섞여 세어지는 것 방지 (크롤 시 _without_images와 동일 기준)
                            if field_name in self.IMAGE_PREVIEW_FIELDS and image_urls and main_image_url:
                                main_key = _image_key(main_image_url)
                                image_urls = [u for u in image_urls if _image_key(u) != main_key]
                        except Exception as exc:
                            error = str(exc)
                    entry = {"url": url, "value": value, "ok": bool(value), "error": error}
                    if image_urls is not None:
                        # 인식 개수와 썸네일 개수가 일치하도록 전부 전달 (상한만 안전장치)
                        entry["imageUrls"] = image_urls[:20]
                        entry["imageCount"] = len(image_urls)
                        entry["ok"] = bool(image_urls)
                    aggregate[field_name].append(entry)
                    completed_fields += 1
            await page.close()
        self.raw_results = aggregate
        self.progress.emit("[progress:1.00] 테스트 완료")
        results: dict = {"__raw_results__": aggregate}
        for field_name, entries in aggregate.items():
            hits = [entry["value"] for entry in entries if entry["value"]]
            results[field_name] = (hits[0] if hits else None) if len(self.test_urls) == 1 else (
                f"{len(hits)}/{len(entries)} 성공 · {str(hits[0])[:60] if hits else '실패'}"
            )
        return results

    async def _extract_test_option(self, page, adapter, field_name: str) -> str | None:
        options = adapter.adapter.options
        group = options.groups[0] if options.groups else None
        if field_name == "option_prices" and options.option_price_delta:
            value, _ = await self._extract_test_field(page, options.option_price_delta)
            return value
        if group is None:
            return None
        elements = await page.query_selector_all(group.values_selector)
        reads = [await self._read_test_option_value(el, group) or "" for el in elements]
        if field_name == "option_prices":
            prices = [
                parsed.price_delta if parsed.price_delta is not None else parsed.supply_price
                for parsed in (parse_option_text(item, options.option_text_parser) for item in reads)
                if parsed.price_delta is not None or parsed.supply_price is not None
            ]
            if not prices:
                return None
            preview = ", ".join(str(price) for price in prices[:5])
            return f"{len(prices)}개 · {preview}"
        # 병합 표시: '3개 · S, M, L / +0원, +10,000원, +20,000원' (값 묶음 / 가격 묶음, 개수 항상 일치)
        parsed = [parse_option_text(item, options.option_text_parser) for item in reads]
        summary = format_option_group(parsed)
        if not summary:
            return None
        # 옵션 품절 노출: 라이브 검증/미리보기에 품절 개수 표기 (placeholder 제외).
        soldout = 0
        for el, text in zip(elements, reads):
            if text and not is_option_placeholder(text) and await option_is_soldout(el, text):
                soldout += 1
        if soldout:
            summary = f"{summary} (품절 {soldout})"
        return summary[:200]

    async def _login(self, page) -> None:
        from app.analyzer.login_helper import perform_login as _login_shared
        assert self.login_url and self.username and self.password  # guarded by caller
        self.progress.emit("로그인 중...")
        await _login_shared(page, self.login_url, self.username, self.password, on_progress=self.progress.emit)

    async def _extract_test_field(self, page, extractor, field_name: str = "") -> tuple[str | None, list[str] | None]:
        if extractor.selector:
            if field_name in self.IMAGE_PREVIEW_FIELDS:
                # 상세/추가 이미지: 크롤과 동일 헬퍼로 크기 측정 → 버튼·아이콘 제외. 개수·내용이 크롤과 일치.
                values = await collect_detail_images(page, extractor.selector)
                if extractor.skip_first:
                    values = values[extractor.skip_first:]
                urls = [urljoin(page.url, item) for item in values]
                return f"{len(urls)}개 인식", urls
            if extractor.multiple:
                elements = await page.query_selector_all(extractor.selector)
                # ponytail: reads all matched elements for an accurate count; cap if a selector ever matches hundreds
                reads = [await self._read_test_element(el, extractor) or "" for el in elements]
                values = [item for item in reads if item]
                if not values and extractor.attribute in ("src", "data-src"):
                    # 컨테이너 박스 선택자 폴백 — YAMLAdapter._extract_field와 동일 기준
                    elements = await page.query_selector_all(extractor.selector + " img")
                    reads = [await self._read_test_element(el, extractor) or "" for el in elements]
                    values = [item for item in reads if item]
                if extractor.skip_first:
                    values = values[extractor.skip_first:]
                if values:
                    values = [clean_field_value(field_name, item) or item for item in values]
                    preview = ", ".join(item[:50] for item in values[:5])
                    return f"{len(values)}개 · {preview}", None
            else:
                element = await page.query_selector(extractor.selector)
                if element:
                    value = await self._read_test_element(element, extractor)
                    if value:
                        # 라벨 오염 정리(원산지/이름/코드 등)를 transform 전에 적용.
                        value = clean_field_value(field_name, value) or value
                        if extractor.transform == "extract_number":
                            match = re.search(r"-?\d[\d,]*", value)
                            value = match.group().replace(",", "") if match else value
                        return value.strip()[:100], None
        value = await self._extract_test_fallback_from(page, extractor)
        if value is None:
            value = extractor.fallback or None
        if value and extractor.transform == "extract_number":
            match = re.search(r"-?\d[\d,]*", value)
            value = match.group().replace(",", "") if match else value
        return (value.strip()[:100] if value else None), None

    async def _read_test_element(self, element, extractor) -> str | None:
        if extractor.html:
            return await element.inner_html()
        if extractor.attribute:
            value = await element.get_attribute(extractor.attribute)
            return value or (await element.get_attribute(extractor.fallback_attribute) if extractor.fallback_attribute else None)
        return await element.inner_text()

    async def _read_test_option_value(self, element, group_config) -> str | None:
        if group_config.value_text == "value":
            return await element.get_attribute("value")
        if group_config.value_text == "attribute" and group_config.value_attribute:
            return await element.get_attribute(group_config.value_attribute)
        return await element.inner_text()

    async def _extract_test_fallback_from(self, page, extractor) -> str | None:
        if extractor.fallback_from == "url":
            return extract_url_value(page.url, extractor)
        if extractor.fallback_from == "maxq":
            maxq = await page.query_selector("input[name='maxq']")
            return _status_from_maxq_value(await maxq.get_attribute("value")) if maxq else None
        if extractor.fallback_from == "cart_button":
            return await status_from_cart_button(page, extractor.selector)
        return None


TestWorker = AdapterTestWorker


class OptionTextParserAnalyzeWorker(_AsyncWorker):
    finished = Signal(dict)

    def __init__(self, request: OptionTextParserAnalyzeRequest) -> None:
        super().__init__()
        self.request = request

    def run(self) -> None:
        try:
            self._run_async(self._analyze(), self.finished.emit)
        finally:
            self.request.password = None

    async def _analyze(self) -> dict:
        import json
        from app.analyzer.llm_client import get_llm_client
        from app.config import load_config
        from app.crawlers.engine import create_engine
        from app.crawlers.registry import load_adapter_from_text

        adapter = load_adapter_from_text(self.request.yaml_text)
        group = adapter.adapter.options.groups[0] if adapter.adapter.options.groups else None
        if group is None or not group.values_selector.strip():
            raise ValueError("옵션값 선택자를 먼저 매핑하세요.")

        state = self.request.storage_state
        if state is None and self.request.supplier_key:
            try:
                from app.analyzer.session_store import load_session_state
                state = load_session_state(self.request.supplier_key)
            except Exception:
                pass

        async with create_engine(headless=True, storage_state=state) as engine:
            page = await engine.new_page()
            if self.request.login_url and self.request.username and self.request.password and state is None:
                from app.analyzer.login_helper import perform_login as _login_shared
                await _login_shared(page, self.request.login_url, self.request.username, self.request.password)
            await page.goto(self.request.target_url, wait_until="domcontentloaded", timeout=15_000)
            await page.wait_for_timeout(1000)
            elements = await page.query_selector_all(group.values_selector)
            examples: list[str] = []
            for el in elements[:30]:
                if group.value_text == "value":
                    text = await el.get_attribute("value")
                elif group.value_text == "attribute" and group.value_attribute:
                    text = await el.get_attribute(group.value_attribute)
                else:
                    text = await el.inner_text()
                text = " ".join(str(text or "").split())
                if text and not is_option_placeholder(text):
                    examples.append(text[:200])
            await page.close()

        if not examples:
            raise ValueError("옵션 샘플 텍스트를 찾지 못했습니다.")

        client = get_llm_client(load_config().llm_provider)
        system_prompt = (
            "당신은 도매 쇼핑몰 옵션 텍스트 파서 설계자입니다. "
            "옵션 텍스트 예시에서 옵션값과 가격을 분리하는 Python 정규식을 만드세요.\n\n"
            "반드시 JSON만 응답하세요:\n"
            '{"enabled": true, "pattern": "정규식", "price_kind": "delta|supply", '
            '"confidence": "high|medium|low", "examples": ["예시"]}\n\n'
            "규칙:\n"
            "1. pattern에는 named group (?P<value>...), (?P<price>...)가 반드시 있어야 합니다.\n"
            "2. 부호가 가격과 분리되어 있으면 (?P<sign>[+-])를 사용하세요.\n"
            "3. 가격이 추가금/차감금이면 price_kind=delta, 옵션 공급가 자체면 supply입니다.\n"
            "4. 확신이 없으면 confidence=low로 응답하세요.\n"
            "5. JSON 외 텍스트는 출력하지 마세요."
        )
        user_prompt = "옵션 텍스트 예시:\n" + "\n".join(f"- {item}" for item in examples)
        response = await client.generate(system_prompt, user_prompt)
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            text = "\n".join(lines[1:end]).strip()
        result = json.loads(text)

        pattern = str(result.get("pattern") or "").strip()
        price_kind = str(result.get("price_kind") or "delta").strip()
        confidence = str(result.get("confidence") or "low").strip()
        if price_kind not in {"delta", "supply"}:
            price_kind = "delta"
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"
        if not pattern or "?P<value>" not in pattern or "?P<price>" not in pattern:
            raise ValueError("AI가 유효한 옵션 파서 정규식을 만들지 못했습니다.")
        if confidence == "low":
            raise ValueError("AI 옵션 분석 신뢰도가 낮습니다. 옵션값 선택자를 다시 확인하세요.")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"AI 옵션 파서 정규식 오류: {exc}") from exc

        parser = {
            "enabled": True,
            "pattern": pattern,
            "price_kind": price_kind,
            "confidence": confidence,
            "examples": examples[:10],
        }
        parsed = [parse_option_text(item, parser, use_legacy=False) for item in examples[:5]]
        if not any(item.value and (item.price_delta is not None or item.supply_price is not None) for item in parsed):
            raise ValueError("AI 옵션 파서가 샘플 옵션을 분리하지 못했습니다.")
        return {"parser": parser, "examples": examples[:10]}


@dataclass
class PickerValidateRequest:
    picked_element: Any  # PickedElement from element_picker
    field_path: str
    field_label: str


IMAGE_PICKER_FIELD_PATHS = {"adapter.product.detail_content", "adapter.product.extra_image_urls"}


class PickerValidateWorker(_AsyncWorker):
    """LLM-assisted validation of a user-picked element's CSS selector.

    Runs after the user clicks an element in the picker. Sends the selector
    candidates + match counts + element text to the LLM, which returns a
    validated selector, confidence level, and a short note. The view-model
    uses the validated selector (when confidence is high/medium) in place of
    the rule-based ``choose_best_selector`` output.
    """

    finished = Signal(dict)

    def __init__(self, request: PickerValidateRequest) -> None:
        super().__init__()
        self.request = request

    def run(self) -> None:
        self._run_async(self._validate(), self.finished.emit)

    async def _validate(self) -> dict:
        import json
        from app.analyzer.llm_client import get_llm_client
        from app.config import load_config

        picked = self.request.picked_element
        candidates = list(picked.selector_candidates or [])[:6]
        counts = dict(picked.match_counts or {})
        text = (picked.text or "")[:200]
        html_preview = (picked.html_preview or "")[:300]

        if not candidates:
            return {
                "validated_selector": picked.selector,
                "confidence": "low",
                "note": "선택자 후보 없음",
                "original_selector": picked.selector,
            }

        config = load_config()
        provider = config.llm_provider
        client = get_llm_client(provider)

        if self.request.field_path in IMAGE_PICKER_FIELD_PATHS:
            return await self._validate_image_selector(client, candidates, counts)

        system_prompt = (
            "당신은 웹 크롤링 CSS 선택자 검증 전문가입니다. "
            "사용자가 브라우저에서 클릭한 요소의 선택자 후보와 매치 카운트를 분석하여 "
            "가장 안정적인 CSS 선택자 하나를 추천하세요.\n\n"
            "반드시 다음 JSON 형식으로만 응답하세요:\n"
            '{"validated_selector": "CSS선택자", "confidence": "high|medium|low", "note": "간단한 설명"}\n\n'
            "규칙:\n"
            "1. 매치 카운트가 1인 선택자를 최우선으로 선택하세요.\n"
            "2. nth-of-type 경로보다 id, class, 속성 선택자를 선호합니다 (재사용성).\n"
            "3. 신뢰도 기준:\n"
            "   - high: 매치=1, id/class/속성 기반, 안정적\n"
            "   - medium: 매치 2-5, 또는 nth-of-type이지만 단일 매치\n"
            "   - low: 매치>5, 불안정, 또는 확신 없음\n"
            "4. note에는 선택자 안정성이나 주의사항을 100자 이내로 적으세요.\n"
            "5. JSON 외의 다른 텍스트는 출력하지 마세요."
        )
        user_prompt = (
            f"수집할 필드: {self.request.field_label}\n"
            f"페이지 URL: {picked.url}\n"
            f"요소 텍스트: {text}\n"
            f"요소 HTML 미리보기: {html_preview}\n"
            f"선택자 후보와 매치 카운트:\n"
            + "\n".join(f"- {sel} → {counts.get(sel, '?')}개 매치" for sel in candidates)
        )

        try:
            response = await client.generate(system_prompt, user_prompt)
        except Exception as exc:
            return {
                "validated_selector": picked.selector,
                "confidence": "low",
                "note": f"AI 검증 실패: {exc}",
                "original_selector": picked.selector,
            }

        # Strip markdown code fences if present
        text_resp = response.strip()
        if text_resp.startswith("```"):
            lines = text_resp.split("\n")
            end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            text_resp = "\n".join(lines[1:end])
        text_resp = text_resp.strip()

        try:
            result = json.loads(text_resp)
        except json.JSONDecodeError:
            return {
                "validated_selector": picked.selector,
                "confidence": "low",
                "note": "AI 응답 파싱 실패",
                "original_selector": picked.selector,
            }

        validated = str(result.get("validated_selector", "")).strip()
        confidence = str(result.get("confidence", "low")).strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"
        note = str(result.get("note", "")).strip()[:200]

        # Fallback to original if LLM returned empty/invalid selector
        if not validated:
            validated = picked.selector
            confidence = "low"

        return {
            "validated_selector": validated,
            "confidence": confidence,
            "note": note,
            "original_selector": picked.selector,
        }

    async def _validate_image_selector(self, client, candidates: list[str], counts: dict) -> dict:
        import json

        picked = self.request.picked_element
        images = list(getattr(picked, "image_candidates", []) or [])[:20]
        field_label = self.request.field_label
        is_detail = self.request.field_path == "adapter.product.detail_content"
        target_rule = (
            "상세 설명 본문에 들어가는 큰 상세 이미지들을 고르세요. "
            "대표 이미지, 썸네일, 추천상품, 배너, 아이콘, 네비게이션 이미지는 제외하세요."
            if is_detail else
            "상품 갤러리의 추가 이미지를 고르세요. 대표 이미지와 상세 설명 본문 이미지, 추천상품, 배너는 제외하세요."
        )
        system_prompt = (
            "당신은 쇼핑몰 DOM에서 상품 이미지 CSS 선택자를 고르는 전문가입니다. "
            "사용자가 이미지들이 들어있는 영역을 클릭했습니다. 후보 selector와 영역 안 이미지 목록을 보고 "
            "가장 적절한 이미지 selector를 하나 고르세요.\n\n"
            "반드시 다음 JSON 형식으로만 응답하세요:\n"
            '{"selector": "CSS선택자", "attribute": "src|data-src", "multiple": true, '
            '"confidence": "high|medium|low", "note": "간단한 설명"}\n\n'
            "규칙:\n"
            f"1. {target_rule}\n"
            "2. selector는 가능하면 제공된 후보 중 하나를 사용하세요.\n"
            "3. 여러 이미지를 수집해야 하므로 multiple은 true로 두세요.\n"
            "4. 이미지 URL이 data-src에만 있으면 attribute는 data-src, 아니면 src를 사용하세요.\n"
            "5. 확신이 없으면 confidence를 low로 주세요.\n"
            "6. JSON 외의 다른 텍스트는 출력하지 마세요."
        )
        image_lines = []
        for idx, item in enumerate(images, 1):
            image_lines.append(
                f"{idx}. selector={item.get('selector', '')}, "
                f"src={item.get('src', '')}, data-src={item.get('dataSrc', '')}, "
                f"alt={item.get('alt', '')}, class={item.get('classes', '')}"
            )
        user_prompt = (
            f"수집할 필드: {field_label}\n"
            f"페이지 URL: {picked.url}\n"
            f"선택 영역 텍스트: {(picked.text or '')[:200]}\n"
            f"선택 영역 HTML 미리보기: {(picked.html_preview or '')[:500]}\n"
            "selector 후보와 매치 카운트:\n"
            + "\n".join(f"- {sel} → {counts.get(sel, '?')}개 매치" for sel in candidates)
            + "\n\n선택 영역 안 이미지 후보:\n"
            + ("\n".join(image_lines) if image_lines else "- 이미지 후보 없음")
        )

        try:
            response = await client.generate(system_prompt, user_prompt)
        except Exception as exc:
            return {
                "validated_selector": picked.selector,
                "selector": picked.selector,
                "attribute": "src",
                "multiple": True,
                "confidence": "low",
                "note": f"AI 이미지 분석 실패: {exc}",
                "original_selector": picked.selector,
            }

        text_resp = response.strip()
        if text_resp.startswith("```"):
            lines = text_resp.split("\n")
            end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            text_resp = "\n".join(lines[1:end])
        text_resp = text_resp.strip()

        try:
            result = json.loads(text_resp)
        except json.JSONDecodeError:
            return {
                "validated_selector": picked.selector,
                "selector": picked.selector,
                "attribute": "src",
                "multiple": True,
                "confidence": "low",
                "note": "AI 이미지 응답 파싱 실패",
                "original_selector": picked.selector,
            }

        selector = str(result.get("selector") or result.get("validated_selector") or "").strip()
        confidence = str(result.get("confidence", "low")).strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"
        attribute = str(result.get("attribute") or "src").strip()
        if attribute not in {"src", "data-src"}:
            attribute = "src"
        note = str(result.get("note", "")).strip()[:200]
        if not selector:
            selector = picked.selector
            confidence = "low"

        return {
            "validated_selector": selector,
            "selector": selector,
            "attribute": attribute,
            "multiple": True,
            "confidence": confidence,
            "note": note,
            "original_selector": picked.selector,
        }


class CategoryMenuProbeWorker(_AsyncWorker):
    finished = Signal(dict)

    def __init__(self, request: CategoryMenuProbeRequest) -> None:
        super().__init__()
        self.request = request

    def run(self) -> None:
        self._run_async(self._probe(), self.finished.emit)

    async def _probe(self) -> dict:
        from app.crawlers.engine import create_engine

        state = self.request.storage_state
        if state is None and self.request.supplier_key:
            try:
                from app.analyzer.session_store import load_session_state
                state = load_session_state(self.request.supplier_key)
            except Exception:
                pass

        selectors = [
            s.strip()
            for s in [self.request.selector, *list(self.request.selector_candidates or [])]
            if str(s or "").strip()
        ]
        selectors = list(dict.fromkeys(selectors))[:8]
        async with create_engine(headless=True, storage_state=state) as engine:
            page = await engine.new_page()
            await page.goto(self.request.url, wait_until="domcontentloaded", timeout=20_000)
            await page.wait_for_timeout(1000)
            categories = await page.evaluate(
                r"""
                (selectors) => {
                  // Walk up from parentElement (not el itself) until we find a container
                  // that holds >= 2 links — this is the category list.
                  // ponytail: avoids closest() self-matching on elements with "cate"/"menu"/"gnb" classes
                  function findContainer(el) {
                    let node = el.parentElement;
                    for (let i = 0; i < 10 && node && node !== document.body; i++) {
                      if (node.querySelectorAll('a[href]').length >= 2) return node;
                      node = node.parentElement;
                    }
                    return el.parentElement || el;
                  }
                  const seen = new Set();
                  const out = [];
                  for (const sel of selectors) {
                    try {
                      for (const el of Array.from(document.querySelectorAll(sel)).slice(0, 5)) {
                        const container = findContainer(el);
                        for (const a of Array.from(container.querySelectorAll('a[href]'))) {
                          const name = (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim();
                          const rawHref = a.getAttribute('href') || '';
                          if (!name || !rawHref || rawHref === '#' || /^javascript:|^mailto:|^tel:/i.test(rawHref)) continue;
                          const url = new URL(rawHref, location.href).href;
                          const key = name + '\n' + url;
                          if (seen.has(key)) continue;
                          seen.add(key);
                          out.push({name, url});
                          if (out.length >= 50) return out;
                        }
                      }
                    } catch (_) {}
                  }
                  return out;
                }
                """,
                selectors,
            )
        return {
            "categories": categories or [],
            "selector": self.request.selector,
            "url": self.request.url,
        }


# ── 전체 자동화 어댑터 워커 ──────────────────────────────────────────────────
# auto_adapter.run_auto_adapter 오케스트레이터를 실제 브라우저/LLM 작업으로 감싼다.
# 사람 개입이 필요한 지점(카테고리/특정 필드 미확정)은 finished 페이로드의 "unresolved"
# 로 전달해 뷰모델이 기존 피커를 재사용해 후속 처리하게 한다.

_AUTO_REPAIR_FIELD_HINTS = {
    "supplier_product_code": "상품 고유 코드/상품번호 텍스트",
    "raw_product_name": "상품명 제목 텍스트",
    "supply_price": (
        "공급가/가격 숫자 (attribute 비우고 transform: extract_number). "
        "가격 라벨이 여러 개인 컨테이너 선택자 금지 — 판매가격·공급가 라벨의 값 요소만 선택. "
        "취소선 소비자가/정가/시중가 요소는 공급가가 아님"
    ),
    "origin": "원산지 텍스트 (예: 국산/중국). 판매가/배송비 컨테이너 금지",
    "main_image_url": "대표 상품 이미지 img (attribute: src, 없으면 data-src)",
    "detail_content": "상세 설명 본문 이미지 컨테이너의 img (multiple)",
    "extra_image_urls": "상품 갤러리 추가 이미지 img (multiple)",
    "option_values": "옵션값(예: 색상/사이즈) 요소",
    "option_prices": "옵션 추가금액 요소 (transform: extract_number)",
}

_AUTO_REPAIR_SYSTEM_PROMPT = (
    "당신은 웹 스크래핑 CSS 선택자 교정 전문가입니다. 지정된 한 필드의 선택자가 "
    "실제 페이지에서 실패했습니다. DOM 을 다시 분석해 더 정확한 CSS 선택자를 찾으세요.\n\n"
    "반드시 다음 JSON 형식으로만 응답하세요 (설명·코드블록 없이):\n"
    '{"selector": "CSS선택자", "attribute": "src|data-src|value 또는 빈문자열", '
    '"transform": "extract_number 또는 빈문자열"}\n\n'
    "규칙:\n"
    "1. 값을 찾을 수 없으면 selector 를 빈 문자열로 두세요.\n"
    "2. 이미지 필드는 img 를 가리키고 attribute 는 src(없으면 data-src)로 하세요.\n"
    "3. 가격/추가금액은 attribute 를 비우고 transform 을 extract_number 로 하세요.\n"
    "4. JSON 외 텍스트 출력 금지."
)

_JUDGE_SYSTEM_PROMPT = (
    "당신은 쇼핑몰 크롤링 추출값 검수자입니다. 각 필드의 샘플 추출값들이 그 필드의 값으로 "
    "타당한지 사람이 직접 보듯 판정하세요. 각 값이 그 필드명으로 자연스러운지, 그리고 필드끼리 "
    "교차 비교했을 때 모순이 없는지 함께 보세요.\n\n"
    "불합격 기준 예시:\n"
    "- 상품코드가 상품명과 동일한 값이거나, 조사·괄호가 섞인 문장형(예: '비가(VIGA) 쇼핑카트 (V50672)')인 경우 "
    "— 코드는 보통 짧은 식별자입니다\n"
    "- 상품명이 사업자번호/통신판매업신고번호/네비게이션/버튼/푸터 고정 문구인 경우\n"
    "- 가격이 0이거나 전화번호·사업자번호처럼 보이는 경우\n"
    "- 공급가에 취소선 소비자가/정가/시중가 값이 잡힌 경우 — 판매가격/공급가 라벨의 값이 진짜 공급가입니다\n"
    "- 원산지에 '원산지 :' 같은 라벨이 남아 있거나 브랜드·판매가·배송 정보가 섞인 경우 "
    "— 순수 국가/지역명이어야 합니다\n"
    "- 상품코드가 URL 전체이거나 안내 문구인 경우\n"
    "- 이미지 URL이 로고/배너/아이콘 파일명인 경우\n\n"
    "반드시 다음 JSON 형식으로만 응답하세요 (모든 입력 필드키 포함, JSON 외 텍스트 금지):\n"
    '{"필드키": {"ok": true|false, "reason": "불합격 사유 (합격이면 빈 문자열)"}}'
)


def _classify_status(snap: dict) -> str:
    """스냅샷 신호로 판매중/품절 분류. auto 모드가 후보 쌍을 스스로 찾는 데 쓴다.

    '품절' 텍스트(explicit_soldout)는 네비/연관상품에서 오탐이 나므로 단독 신호로 쓰지 않는다:
    sold_out ⟺ maxq==0 또는 (explicit_soldout 이면서 구매 버튼 없음). 신호 충돌은 unknown.
    """
    maxq = str(snap.get("maxq_value") or "").strip()
    explicit = bool(snap.get("explicit_soldout"))
    has_buy = bool(snap.get("has_buy_button"))
    if maxq == "0" or (explicit and not has_buy):
        return "sold_out"
    if has_buy and not explicit:
        return "available"
    return "unknown"  # explicit + 구매버튼 동시 존재 등 신호 충돌


_MANUAL_LOGIN_TIMEOUT_SEC = 300  # 수동 로그인 대기 상한 (PickerJob과 동일 관례)


class AutoAdapterWorker(_AsyncWorker):
    finished = Signal(dict)
    login_required = Signal()

    def __init__(self, request: AutoAdapterRequest) -> None:
        super().__init__()
        self.request = request
        self._state: dict | None = None
        self._detail_dom: str = ""
        self._option_dom: str = ""              # 옵션 페이지 축약 DOM (option_url 지정 시)
        self._detail_screenshot_path: str = ""  # probe가 저장한 상세 페이지 스크린샷 경로
        self._shots_dir: str | None = None
        self._manual_login_event: asyncio.Event | None = None
        self._manual_login_cancelled = False

    def run(self) -> None:
        try:
            self._run_async(self._orchestrate(), self.finished.emit)
        finally:
            self.request.password = None

    @Slot()
    def confirmManualLogin(self) -> None:
        """User confirmed they logged in manually in the headful browser — resume."""
        self._wake_manual_login()

    @Slot()
    def cancelManualLogin(self) -> None:
        """User cancelled the manual-login prompt — abort the run."""
        self._manual_login_cancelled = True
        self._wake_manual_login()

    def _wake_manual_login(self) -> None:
        # GUI 스레드에서 호출됨 — asyncio.Event를 워커 루프에서 스레드 안전하게 set.
        loop, event = self._loop, self._manual_login_event
        if loop is not None and event is not None and loop.is_running():
            loop.call_soon_threadsafe(event.set)

    async def _manual_login_probe(self):
        """자동 로그인 실패 시: 헤드풀 브라우저로 사람이 직접 로그인하게 하고,
        확인되면 획득한 세션으로 자격증명 없이 probe_site를 재실행한다."""
        from app.analyzer.login_helper import (
            _check_logout_indicators,
            _has_visible_password_input,
            _safe_goto,
        )
        from app.analyzer.site_probe import probe_site
        from app.crawlers.engine import create_engine

        self._manual_login_cancelled = False
        self._manual_login_event = asyncio.Event()
        async with create_engine(headless=False) as engine:
            page = await engine.new_page()
            await _safe_goto(page, self.request.login_url)
            self.login_required.emit()
            self.progress.emit("자동 로그인 실패 — 브라우저에서 직접 로그인 후 확인 버튼을 눌러주세요.")
            try:
                await asyncio.wait_for(
                    self._manual_login_event.wait(), timeout=_MANUAL_LOGIN_TIMEOUT_SEC
                )
            except asyncio.TimeoutError:
                raise RuntimeError("수동 로그인 대기 시간이 초과되었습니다 (5분).")
            if self._manual_login_cancelled:
                raise RuntimeError("수동 로그인이 취소되었습니다.")
            logged_in = await _check_logout_indicators(page) or not await _has_visible_password_input(page)
            if not logged_in:
                raise RuntimeError("로그인이 완료되지 않은 것 같습니다. 다시 시도해주세요.")
            storage_state = await page.context.storage_state()

        self.progress.emit("[progress:0.00] 로그인 세션으로 사이트 재분석 중...")
        return await probe_site(
            self.request.main_url, self.request.listing_url, self.request.detail_url,
            headless=True, on_progress=self.progress.emit, storage_state=storage_state,
        )

    def _emit_event(self, kind: str, **payload) -> None:
        from app.analyzer.auto_adapter import _event_line
        self.progress.emit(_event_line(kind, **payload))

    async def _orchestrate(self) -> dict:
        from app.analyzer.auto_adapter import AutoAdapterDeps, run_auto_adapter
        from app.analyzer.site_probe import probe_site

        self._emit_event("stage", stage="probe", status="active", label="사이트 분석")
        self.progress.emit("[progress:0.00] 사이트 분석 중...")
        try:
            probe = await probe_site(
                self.request.main_url, self.request.listing_url, self.request.detail_url,
                headless=True, on_progress=self.progress.emit,
                login_url=self.request.login_url, username=self.request.username,
                password=self.request.password,
            )
        except RuntimeError:
            # 자동 로그인(폼 휴리스틱 + LLM)이 모두 실패. 자격증명이 있을 때만
            # 사람에게 헤드풀 브라우저 직접 로그인을 딱 한 번 요청한다.
            has_login = bool(
                self.request.login_url and self.request.username and self.request.password
            )
            if not has_login:
                raise
            probe = await self._manual_login_probe()
        self._emit_event("stage", stage="probe", status="done", label="사이트 분석")
        self._state = getattr(probe, "storage_state", None)
        self._detail_dom = getattr(probe, "detail_html", "") or ""
        self._detail_screenshot_path = getattr(probe, "detail_screenshot_path", "") or ""
        if self._state and self.request.supplier_key:
            try:
                from app.analyzer.session_store import save_session_state
                save_session_state(self.request.supplier_key, self._state)
            except Exception:
                pass

        urls = [str(item["url"]) for item in (probe.sample_products or []) if item.get("url")]
        detail = str(self.request.detail_url or "").strip()
        if detail and detail not in urls:
            urls = [detail, *urls]

        # 옵션 있는 상품 URL을 받았으면 그 페이지 DOM을 확보해 옵션 evidence/검증/재선택 기준으로 쓴다.
        option_url = str(self.request.option_url or "").strip()
        option_dom: str | None = None
        option_test_urls: list[str] | None = None
        if option_url:
            option_dom = await self._fetch_option_dom(option_url)
            self._option_dom = option_dom or ""
            option_test_urls = [option_url]

        deps = AutoAdapterDeps(
            generate=lambda: self._dep_generate(probe),
            test_fields=self._dep_test_fields,
            repair_field=self._dep_repair_field,
            find_status_pair=self._dep_find_status_pair,
            compare_status=self._dep_compare_status,
            analyze_options=self._dep_analyze_options,
            judge_values=self._dep_judge_values,
        )
        result = await run_auto_adapter(
            probe, self.request.supplier_name, deps,
            test_urls=urls, on_progress=self.progress.emit,
            option_dom=option_dom, option_test_urls=option_test_urls,
        )
        return {
            "yaml": result.yaml_text,
            "unresolved": list(result.unresolved_fields),
            "log": list(result.log),
            "status_pair": list(result.status_pair) if result.status_pair else None,
            "dispositions": dict(result.dispositions),
            "needs_login": bool(getattr(probe, "needs_login", False)),
            "probe": probe,
        }

    async def _fetch_option_dom(self, option_url: str) -> str | None:
        """옵션 있는 상품 페이지에 헤드리스로 접속해 축약 DOM을 확보. 실패 시 None + note."""
        from app.analyzer.html_reducer import reduce_html
        from app.crawlers.engine import create_engine
        try:
            async with create_engine(headless=True, storage_state=self._state) as engine:
                page = await engine.new_page()
                await page.goto(option_url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1200)
                content = await page.content()
                await page.close()
            return reduce_html(content)
        except Exception as exc:
            self.progress.emit(f"옵션 페이지 DOM 확보 실패, 기본 상세 DOM 사용: {exc}")
            return None

    async def _dep_generate(self, probe) -> str:
        res = await generate_adapter_yaml(
            probe, self.request.supplier_name,
            llm_provider=self.request.provider, auto_fallback=self.request.auto_fallback,
            on_progress=self.progress.emit, include_manual_fields=True,
        )
        return res.yaml_text

    async def _dep_test_fields(self, yaml_text, urls, fields):
        req = AdapterTestRequest(
            yaml_text, list(urls), "", self.request.login_url,
            self.request.username, self.request.password, tuple(fields),
            storage_state=self._state, supplier_key=self.request.supplier_key,
        )
        if self._shots_dir is None:
            self._shots_dir = tempfile.mkdtemp(prefix="auto_adapter_shots_")

        def _on_shot(url: str, path: str) -> None:
            self._emit_event("visit", url=url, purpose="라이브 검증")
            self._emit_event("shot", path=path, url=url, field="")

        result = await AdapterTestWorker(
            req, screenshot_dir=self._shots_dir, on_screenshot=_on_shot,
        )._run_test()
        return result.get("__raw_results__", {})

    async def _dep_judge_values(self, samples: dict[str, list[str]]) -> dict[str, dict]:
        """1차 통과 필드들의 추출값 타당성 LLM 검수. 예외는 오케스트레이터가 통과로 처리."""
        from app.analyzer.llm_client import QuotaExceededError, get_llm_client

        user = "필드별 샘플 추출값:\n" + json.dumps(samples, ensure_ascii=False, indent=1)
        provider = self.request.provider
        try:
            resp = await get_llm_client(provider).generate(_JUDGE_SYSTEM_PROMPT, user)
        except QuotaExceededError:
            if not self.request.auto_fallback:
                raise
            provider = "openai" if provider == "gemini" else "gemini"
            resp = await get_llm_client(provider).generate(_JUDGE_SYSTEM_PROMPT, user)
        verdicts = json.loads(_strip_json_response(resp))
        return verdicts if isinstance(verdicts, dict) else {}

    async def _dep_repair_field(self, yaml_text, field, feedback) -> str:
        import yaml as _yaml
        from app.analyzer.adapter_generator import _strip_empty_selectors
        from app.analyzer.adapter_schema import Adapter
        from app.analyzer.llm_client import QuotaExceededError, get_llm_client
        from app.analyzer.mapping_hints import MappingHint, apply_locked_hints_to_yaml_dict

        is_option = field.test_key in ("option_values", "option_prices")
        # 옵션 필드는 옵션 페이지 DOM 기준으로 재선택 (있으면), 나머지는 상세 DOM.
        dom = self._option_dom if (is_option and self._option_dom) else self._detail_dom
        if not dom:
            return yaml_text
        hint_desc = _AUTO_REPAIR_FIELD_HINTS.get(field.test_key, field.field_path)
        user = (
            f"필드: {field.field_path}\n설명: {hint_desc}\n\n{feedback}\n\n"
            f"## 상품 상세 페이지 DOM\n{dom[:12000]}"
        )
        # 비전 계약 선반영: 상세 스크린샷이 있으면 image_paths로 넘긴다 (옵션 필드는 상세 스크린샷
        # 무관하므로 생략). kwarg는 값이 있을 때만 — 기존 generate 시그니처와도 호환되게.
        img_kw = (
            {"image_paths": [self._detail_screenshot_path]}
            if self._detail_screenshot_path and not is_option else {}
        )
        provider = self.request.provider
        try:
            resp = await get_llm_client(provider).generate(_AUTO_REPAIR_SYSTEM_PROMPT, user, **img_kw)
        except QuotaExceededError:
            if not self.request.auto_fallback:
                return yaml_text
            provider = "openai" if provider == "gemini" else "gemini"
            resp = await get_llm_client(provider).generate(_AUTO_REPAIR_SYSTEM_PROMPT, user, **img_kw)
        try:
            spec = json.loads(_strip_json_response(resp))
        except json.JSONDecodeError:
            return yaml_text
        if not isinstance(spec, dict):
            return yaml_text
        selector = str(spec.get("selector") or "").strip()
        if not selector:
            return yaml_text
        kwargs: dict = {
            "page_kind": field.page_kind, "field_path": field.field_path,
            "chosen_selector": selector, "locked": True,
        }
        for key in ("attribute", "transform"):
            value = str(spec.get(key) or "").strip()
            if value:
                kwargs[key] = value
        if field.test_key in ("detail_content", "extra_image_urls"):
            kwargs["multiple"] = True
        try:
            hint = MappingHint(**kwargs)
        except ValueError:
            return yaml_text
        raw = _yaml.safe_load(yaml_text) or {}
        try:
            apply_locked_hints_to_yaml_dict(raw, [hint])
            _strip_empty_selectors(raw)
            adapter = Adapter.model_validate(raw)
        except Exception:
            return yaml_text
        return _yaml.safe_dump(adapter.model_dump(mode="json", exclude_none=True), allow_unicode=True, sort_keys=False)

    async def _dep_find_status_pair(self, urls):
        from app.analyzer.auto_adapter import AUTO_STATUS_SCAN_MAX
        from app.analyzer.html_reducer import reduce_html
        from app.analyzer.login_helper import perform_login as _login_shared
        from app.crawlers.engine import create_engine

        snap = SoldoutCompareWorker(SoldoutCompareRequest(
            "", "", "", None, None, None, self._state, self.request.supplier_key,
        ))
        # 사용자가 품절 URL을 직접 준 경우: 자동 탐색을 건너뛰고 (판매중, 품절) 쌍을 고정한다.
        fixed_soldout = str(self.request.soldout_url or "").strip()
        available = soldout = None
        async with create_engine(headless=True, storage_state=self._state) as engine:
            page = await engine.new_page()
            if (self.request.login_url and self.request.username and self.request.password
                    and self._state is None):
                await _login_shared(
                    page, self.request.login_url, self.request.username, self.request.password,
                    on_progress=self.progress.emit,
                )
            if fixed_soldout:
                available = str(self.request.detail_url or "").strip() or (urls[0] if urls else None)
                soldout = fixed_soldout
                # 입력한 품절 URL이 실제 품절 신호를 보이는지 확인 (없어도 compare는 진행).
                try:
                    snapshot = await snap._snapshot(page, fixed_soldout, reduce_html)
                    if _classify_status(snapshot) != "sold_out":
                        self.progress.emit("입력한 품절 상품에서 품절 신호를 찾지 못했습니다.")
                except Exception:
                    pass
            else:
                for url in list(urls)[:AUTO_STATUS_SCAN_MAX]:
                    try:
                        snapshot = await snap._snapshot(page, url, reduce_html)
                    except Exception:
                        continue
                    cls = _classify_status(snapshot)
                    if cls == "available" and available is None:
                        available = url
                    elif cls == "sold_out" and soldout is None:
                        soldout = url
                    if available and soldout:
                        break
            await page.close()
        return (available, soldout) if available and soldout else None

    async def _dep_compare_status(self, yaml_text, available, soldout) -> dict:
        req = SoldoutCompareRequest(
            yaml_text, available, soldout, self.request.login_url,
            self.request.username, self.request.password, self._state, self.request.supplier_key,
        )
        return await SoldoutCompareWorker(req)._compare()

    async def _dep_analyze_options(self, yaml_text, url):
        req = OptionTextParserAnalyzeRequest(
            yaml_text, url, self.request.login_url,
            self.request.username, self.request.password, self._state, self.request.supplier_key,
        )
        try:
            result = await OptionTextParserAnalyzeWorker(req)._analyze()
            return result.get("parser")
        except Exception:
            return None
