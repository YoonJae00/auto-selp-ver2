import pytest
from httpx import ASGITransport, AsyncClient

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
