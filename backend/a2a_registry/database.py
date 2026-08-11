from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_session_factory():
    # Readiness must fail fast during local development when PostgreSQL is not
    # running; it must not leave health probes hanging on a driver timeout.
    engine = create_engine(get_settings().database_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


SessionLocal = make_session_factory()


def get_db():
    with SessionLocal() as session:
        yield session
