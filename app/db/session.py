import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    logger.warning("DATABASE_URL is not set in environment. Using safe local fallback for server startup.")
    DATABASE_URL = "sqlite:///./fallback.db"

# Ensure proper dialect prefix for SQLAlchemy (postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

try:
    if DATABASE_URL.startswith("sqlite"):
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10
        )
except Exception as e:
    logger.error(f"Failed to initialize database engine with provided URL ({e}). Falling back to SQLite.")
    engine = create_engine("sqlite:///./fallback.db", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency helper to yield a DB session and close it cleanly."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
