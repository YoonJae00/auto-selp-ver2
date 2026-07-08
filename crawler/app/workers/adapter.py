from __future__ import annotations

import asyncio
import json
import queue
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Coroutine
from urllib.parse import urljoin

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.analyzer.adapter_generator import generate_adapter_yaml, repair_adapter_fields
from app.analyzer.adapter_schema import extract_url_value
from app.analyzer.option_text_parser import is_option_placeholder, parse_option_text, format_option_group
from app.analyzer.picker_session import PickerSession
from app.analyzer.site_probe import probe_site
from app.crawlers.yaml_adapter import _image_key, _status_from_maxq_value, collect_detail_images


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
    if available.get("has_buy_button") and not soldout.get("has_buy_button"):
        return {
            "selector": "",
            "fallback_from": "cart_button",
            "mapping": {"available": "available", "sold_out": "sold_out"},
            "default": "available",
            "confidence": "medium",
            "note": "판매중 상품에만 구매/장바구니 버튼이 있습니다.",
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
        explicit = await self._collect_matches(
            page,
            "img[src*='soldout'], img[src*='sold_out'], img[alt*='품절'], img[alt*='soldout'], "
            ":text('품절'), :text('soldout'), :text('완판')",
        )
        buy_buttons = await self._collect_matches(
            page,
            "button:has-text('장바구니'), button:has-text('구매'), button:has-text('주문'), "
            "input[type='button'][value*='구매'], input[type='submit'][value*='구매'], "
            "input[type='image'][src*='cart'], input[type='image'][src*='buy'], "
            "img[src*='cart'], img[src*='buy'], img[src*='order'], img[src*='purchase']",
        )
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

    def __init__(self, request: AdapterTestRequest) -> None:
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
        self.raw_results: dict[str, list[dict]] = {}

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
        return summary[:200] if summary else None

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
                    preview = ", ".join(item[:50] for item in values[:5])
                    return f"{len(values)}개 · {preview}", None
            else:
                element = await page.query_selector(extractor.selector)
                if element:
                    value = await self._read_test_element(element, extractor)
                    if value:
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
            soldout = await page.query_selector("img[src*='soldout'], img[src*='sold_out'], img[alt*='품절'], img[alt*='soldout'], :text('품절'), :text('soldout'), :text('완판')")
            if soldout:
                return "sold_out"
            cart = await page.query_selector("button:has-text('장바구니'), button:has-text('구매'), button:has-text('주문'), input[type='image'][src*='cart'], input[type='image'][src*='buy'], img[src*='cart'], img[src*='buy'], img[src*='order'], img[src*='purchase']")
            return "available" if cart else None
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
