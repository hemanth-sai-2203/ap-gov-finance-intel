import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.db.session import Base

# NOTE: No pgvector import needed here.
# ALL vector embeddings are stored EXCLUSIVELY in Weaviate Cloud (10GB).
# Supabase PostgreSQL stores ONLY structured SQL metadata — no embedding columns.


class DocumentModel(Base):
    """
    Tracks metadata for each downloaded PDF document.
    Stored in Supabase SQL — no vectors here.
    """
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    category = Column(String(100), nullable=False, index=True)  # e.g. "budget_speech", "finance_manual"
    financial_year = Column(String(20), nullable=True, index=True)  # e.g. "2024-25", "2026-27"
    language = Column(String(20), nullable=True, default="english")  # "english" only (Telugu skipped)
    source_url = Column(String(1000), nullable=True, unique=True)
    local_path = Column(String(1000), nullable=True)
    total_pages = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    status = Column(String(50), default="pending")  # pending, downloaded, processed, failed
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    chunks = relationship("DocumentChunkModel", back_populates="document", cascade="all, delete-orphan")


class DocumentChunkModel(Base):
    """
    Stores chunked text METADATA in Supabase SQL.
    - Content text is stored here for SQL-level filtering/retrieval.
    - NO embedding column — all 768-dim vectors go exclusively to Weaviate Cloud.
    - weaviate_id tracks the corresponding Weaviate object UUID for cross-referencing.
    """
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)   # 1-indexed page number in source PDF
    content = Column(Text, nullable=False)          # Raw chunk text (for SQL full-text access)
    weaviate_id = Column(String(100), nullable=True)  # UUID of corresponding Weaviate vector object
    chunk_metadata = Column(JSON, nullable=True)    # Extra metadata: source, category, year, etc.
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    document = relationship("DocumentModel", back_populates="chunks")


class FinancialRecordModel(Base):
    """
    Stores structured tabular financial data extracted from budget PDFs.
    SQL queries return exact budget numbers — no embedding needed.
    e.g. "What is the total capex allocation for 2026-27?" => SQL GROUP BY query.
    """
    __tablename__ = "financial_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    financial_year = Column(String(20), nullable=False, index=True)  # e.g. "2026-27"
    department = Column(String(255), nullable=False, index=True)      # e.g. "Finance", "School Education"
    scheme_name = Column(String(500), nullable=True)                   # e.g. "Direct Benefit Transfer"
    head_of_account = Column(String(100), nullable=True)
    budget_estimate_cr = Column(Float, nullable=True)                  # In Crores (INR)
    revised_estimate_cr = Column(Float, nullable=True)
    actual_expenditure_cr = Column(Float, nullable=True)
    source_document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    extra_details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
