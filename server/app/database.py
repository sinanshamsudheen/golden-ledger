from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from typing import Generator
from .config import settings


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # test connections before handing to a request
    pool_size=10,             # keep 10 connections open at steady state
    max_overflow=20,          # allow up to 20 extra under burst load
    pool_recycle=300,         # recycle connections every 5 min (Railway proxy drops idle ~10 min)
    pool_timeout=30,          # raise after 30 s if no connection is available
    connect_args={
        "keepalives": 1,
        "keepalives_idle": 60,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "connect_timeout": 10,
    },
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
