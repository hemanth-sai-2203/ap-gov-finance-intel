"""
Andhra Pradesh Government Budget Document Ingestion Pipeline.

Extracts text, structured financial records, and 768-dim embeddings:
- Supabase PostgreSQL: DocumentModel, DocumentChunkModel, FinancialRecordModel
- Weaviate Cloud: 768-dim bge-base-en-v1.5 dense vectors + full-text BM25
"""
import os
import logging
from typing import Optional
from sqlalchemy.orm import Session
from langchain_core.documents import Document

from app.db.session import SessionLocal
from app.db.models import DocumentModel, DocumentChunkModel, FinancialRecordModel
from app.ingestion.pdf_parser import extract_pages_and_text, extract_tables_from_pdf, parse_budget_allocation_rows
from app.ingestion.splitter import split_documents
from app.ingestion.store import store_document_chunks
from app.ingestion.financial_extractor import extract_and_store_financial_records
from app.ingestion.downloader import compute_sha256

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ingest_pdf_document(
    file_path: str,
    title: str,
    financial_year_str: str,
    document_type: str = "budget_volumes",
    source_url: Optional[str] = None,
    department_name: Optional[str] = None
) -> int:
    """
    Ingests a single AP Government PDF document:
    1. Registers DocumentModel in Supabase.
    2. Extracts and splits text pages.
    3. Generates 768-dim embeddings and uploads to Weaviate Cloud + Supabase chunks.
    4. Extracts structured financial records for deterministic SQL queries.
    """
    db: Session = SessionLocal()
    try:
        # 1. Check existing document by URL or title
        existing_doc = None
        if source_url:
            existing_doc = db.query(DocumentModel).filter_by(source_url=source_url).first()

        if not existing_doc:
            doc = DocumentModel(
                title=title,
                category=document_type,
                financial_year=financial_year_str,
                language="english",
                source_url=source_url,
                local_path=file_path,
                status="processing"
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
        else:
            doc = existing_doc
            doc.local_path = file_path

        logger.info(f"Ingesting Document ID {doc.id}: '{title}' ({financial_year_str})")

        # 2. Extract pages text
        pages_data = extract_pages_and_text(file_path)
        doc_pages = []
        for p in pages_data:
            doc_pages.append(Document(
                page_content=p["text"],
                metadata={
                    "page_number": p["page_number"],
                    "document_id": doc.id,
                    "title": title,
                    "financial_year": financial_year_str,
                    "category": document_type
                }
            ))

        doc.total_pages = len(pages_data)
        db.commit()

        # 3. Split and store chunks in Weaviate + Supabase
        chunks, _ = split_documents(doc_pages, chunk_size=2000, chunk_overlap=400)
        chunks_stored = store_document_chunks(doc.id, chunks, db=db)
        doc.total_chunks = chunks_stored
        doc.status = "processed"
        db.commit()

        # 4. Extract structured financial records if budget document
        try:
            records_count = extract_and_store_financial_records(doc.id, db=db)
            logger.info(f"Extracted {records_count} structured financial records for '{title}'.")
        except Exception as fe:
            logger.warning(f"Financial record extraction note: {fe}")

        return doc.id

    except Exception as e:
        db.rollback()
        logger.error(f"Error during document ingestion: {e}")
        raise e
    finally:
        db.close()
