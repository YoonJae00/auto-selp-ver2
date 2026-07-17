import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("NAVER_API_KEY", "test")
os.environ.setdefault("NAVER_SECRET_KEY", "test")
os.environ.setdefault("NAVER_CUSTOMER_ID", "test")
os.environ.setdefault("NAVER_CLIENT_ID", "test")
os.environ.setdefault("NAVER_CLIENT_SECRET", "test")
os.environ.setdefault("Coupang_Access_Key", "test")
os.environ.setdefault("Coupang_Secret_Key", "test")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "internal-test-token")

from database import SessionLocal


def test_session_local_keeps_loaded_attributes_after_commit():
    assert SessionLocal.kw["expire_on_commit"] is False
