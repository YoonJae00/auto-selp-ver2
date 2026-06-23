from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.paths import db_path


def get_engine(db_path_arg: Path | None = None) -> Engine:
    path = db_path_arg or db_path()
    return create_engine(f"sqlite:///{path}", echo=False, future=True)


def init_db(db_path_arg: Path | None = None) -> Engine:
    engine = get_engine(db_path_arg)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine: Engine | None = None) -> Session:
    active_engine = engine or get_engine()
    return sessionmaker(bind=active_engine, expire_on_commit=False)()
