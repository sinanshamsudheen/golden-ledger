from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from typing import Generator
from .config import settings


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # test connections before handing to a request
    pool_size=10,             # keep 10 connections open at steady state
    max_overflow=20,          # allow up to 20 extra under burst load
    pool_recycle=1800,        # recycle connections after 30 min (avoids stale TCP)
    pool_timeout=30,          # raise after 30 s if no connection is available
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
