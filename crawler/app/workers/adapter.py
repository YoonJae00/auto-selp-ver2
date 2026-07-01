from __future__ import annotations

import asyncio
import queue
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Coroutine

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.analyzer.adapter_generator import generate_adapter_yaml
from app.analyzer.picker_session import PickerSession
from app.analyzer.site_probe import probe_site
from app.crawlers.yaml_adapter import _status_from_maxq_value


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
        from app.analyzer.llm_client import get_llm_client
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


class AdapterTestWorker(_AsyncWorker):
    finished = Signal(dict)
    FIELD_NAMES = (
        "supplier_product_code", "raw_product_name",
        "supplier_status", "supply_price", "origin", "main_image_url",
        "detail_content", "extra_image_urls",
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
                for field_name in self.fields:
                    fraction = completed_fields / total_fields if total_fields else 0.0
                    extractor = getattr(product, field_name, None)
                    value = error = None
                    if extractor:
                        self.progress.emit(f"[progress:{fraction:.2f}] 테스트 중: {field_name}")
                        try:
                            value = await self._extract_test_field(page, extractor)
                        except Exception as exc:
                            error = str(exc)
                    aggregate[field_name].append(
                        {"url": url, "value": value, "ok": bool(value), "error": error}
                    )
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

    async def _login(self, page) -> None:
        from app.analyzer.login_helper import perform_login as _login_shared
        assert self.login_url and self.username and self.password  # guarded by caller
        self.progress.emit("로그인 중...")
        await _login_shared(page, self.login_url, self.username, self.password, on_progress=self.progress.emit)

    async def _extract_test_field(self, page, extractor) -> str | None:
        if extractor.selector:
            if extractor.multiple:
                elements = await page.query_selector_all(extractor.selector)
                # ponytail: reads all matched elements for an accurate count; cap if a selector ever matches hundreds
                reads = [await self._read_test_element(el, extractor) or "" for el in elements]
                values = [item for item in reads if item]
                if values:
                    preview = ", ".join(item[:50] for item in values[:5])
                    return f"{len(values)}개 · {preview}"
            else:
                element = await page.query_selector(extractor.selector)
                if element:
                    value = await self._read_test_element(element, extractor)
                    if value:
                        if extractor.transform == "extract_number":
                            match = re.search(r"-?\d[\d,]*", value)
                            value = match.group().replace(",", "") if match else value
                        return value.strip()[:100]
        value = await self._extract_test_fallback_from(page, extractor)
        if value is None:
            value = extractor.fallback or None
        if value and extractor.transform == "extract_number":
            match = re.search(r"-?\d[\d,]*", value)
            value = match.group().replace(",", "") if match else value
        return value.strip()[:100] if value else None

    async def _read_test_element(self, element, extractor) -> str | None:
        if extractor.html:
            return await element.inner_html()
        if extractor.attribute:
            value = await element.get_attribute(extractor.attribute)
            return value or (await element.get_attribute(extractor.fallback_attribute) if extractor.fallback_attribute else None)
        return await element.inner_text()

    async def _extract_test_fallback_from(self, page, extractor) -> str | None:
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


@dataclass
class PickerValidateRequest:
    picked_element: Any  # PickedElement from element_picker
    field_path: str
    field_label: str


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
