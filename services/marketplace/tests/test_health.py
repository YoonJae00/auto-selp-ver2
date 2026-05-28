import pytest
from httpx import ASGITransport, AsyncClient
from pathlib import Path

import main
from main import app


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "marketplace"}


@pytest.mark.asyncio
async def test_create_tables_runs_metadata_create_all_once(monkeypatch):
    class FakeConn:
        def __init__(self):
            self.calls = []

        async def run_sync(self, fn):
            self.calls.append(fn)

    class FakeBegin:
        def __init__(self, conn):
            self.conn = conn

        async def __aenter__(self):
            return self.conn

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def __init__(self):
            self.conn = FakeConn()

        def begin(self):
            return FakeBegin(self.conn)

    fake_engine = FakeEngine()
    monkeypatch.setattr(main, "engine", fake_engine)

    await main.create_tables()

    assert len(fake_engine.conn.calls) == 1
    called_fn = fake_engine.conn.calls[0]
    assert called_fn.__self__ is main.Base.metadata
    assert called_fn.__name__ == "create_all"


@pytest.mark.asyncio
async def test_create_tables_retries_transient_failure_then_succeeds(monkeypatch):
    class FakeConn:
        def __init__(self):
            self.calls = []

        async def run_sync(self, fn):
            self.calls.append(fn)

    class FakeBegin:
        def __init__(self, engine):
            self.engine = engine

        async def __aenter__(self):
            self.engine.begin_calls += 1
            if self.engine.begin_calls <= self.engine.failures_before_success:
                raise ConnectionError("database is starting")
            return self.engine.conn

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def __init__(self, failures_before_success):
            self.failures_before_success = failures_before_success
            self.begin_calls = 0
            self.conn = FakeConn()

        def begin(self):
            return FakeBegin(self)

    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    fake_engine = FakeEngine(failures_before_success=1)
    monkeypatch.setattr(main, "engine", fake_engine)
    monkeypatch.setattr(main, "DB_STARTUP_MAX_ATTEMPTS", 3, raising=False)
    monkeypatch.setattr(main, "DB_STARTUP_RETRY_DELAY_SECONDS", 0.001, raising=False)
    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)

    await main.create_tables()

    assert fake_engine.begin_calls == 2
    assert len(fake_engine.conn.calls) == 1
    assert sleep_calls == [0.001]


@pytest.mark.asyncio
async def test_create_tables_raises_after_retry_attempts_exhausted(monkeypatch):
    class FakeConn:
        async def run_sync(self, fn):
            raise AssertionError("run_sync must not be called when connection fails")

    class FakeBegin:
        def __init__(self, engine):
            self.engine = engine

        async def __aenter__(self):
            self.engine.begin_calls += 1
            raise ConnectionError("database unavailable")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def __init__(self):
            self.begin_calls = 0
            self.conn = FakeConn()

        def begin(self):
            return FakeBegin(self)

    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    fake_engine = FakeEngine()
    monkeypatch.setattr(main, "engine", fake_engine)
    monkeypatch.setattr(main, "DB_STARTUP_MAX_ATTEMPTS", 3, raising=False)
    monkeypatch.setattr(main, "DB_STARTUP_RETRY_DELAY_SECONDS", 0.001, raising=False)
    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)

    with pytest.raises(ConnectionError, match="database unavailable"):
        await main.create_tables()

    assert fake_engine.begin_calls == 3
    assert sleep_calls == [0.001, 0.001]


def test_compose_marketplace_uses_db_health_gating_and_restart_policy():
    compose_path = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    compose_text = compose_path.read_text(encoding="utf-8")

    db_block = compose_text.split("\n  db:\n", 1)[1].split("\n  redis:\n", 1)[0]
    marketplace_block = compose_text.split("\n  marketplace:\n", 1)[1].split(
        "\n  marketplace-worker:\n", 1
    )[0]

    assert "healthcheck:" in db_block
    assert "pg_isready" in db_block

    assert "depends_on:" in marketplace_block
    assert "db:" in marketplace_block
    assert "condition: service_healthy" in marketplace_block
    assert "redis:" in marketplace_block
    assert "condition: service_started" in marketplace_block
    assert "restart:" in marketplace_block
