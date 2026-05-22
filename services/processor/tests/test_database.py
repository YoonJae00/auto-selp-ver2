from database import SessionLocal


def test_session_local_keeps_loaded_attributes_after_commit():
    assert SessionLocal.kw["expire_on_commit"] is False
