import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

# Ensure proper dialect prefix for SQLAlchemy (postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLAlchemy Engine connected to Supabase PostgreSQL
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency helper to yield a DB session and close it cleanly."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
