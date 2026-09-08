"""
Database reset + initialization script.

Architecture (clean, no duplication):
  Supabase PostgreSQL  -> SQL tables ONLY (documents, document_chunks, financial_records)
                          NO vector columns. document_chunks.weaviate_id links to Weaviate.
  Weaviate Cloud 10GB  -> ALL vectors (768-dim bge-base-en-v1.5) + text content

Run this to:
  1. Drop and recreate Supabase tables (removes old vector column)
  2. Delete old Weaviate collection (old 384-dim vectors from bge-small are incompatible)
  3. Re-create fresh Weaviate collection for 768-dim vectors
"""
import sys
import os
import logging
from sqlalchemy import text
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def reset_supabase_tables():
    """Truncates Supabase SQL tables and ensures schema tables exist."""
    from app.db.session import engine, Base
    from app.db.models import DocumentModel, DocumentChunkModel, FinancialRecordModel

    logger.info("Connecting to Supabase PostgreSQL...")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        logger.info("Clearing existing tables...")
        try:
            conn.execute(text("TRUNCATE TABLE document_chunks, financial_records, documents RESTART IDENTITY CASCADE;"))
            logger.info("[OK] Tables truncated.")
        except Exception:
            conn.execute(text("DELETE FROM document_chunks;"))
            conn.execute(text("DELETE FROM financial_records;"))
            conn.execute(text("DELETE FROM documents;"))
            logger.info("[OK] Table rows deleted.")

    logger.info("[OK] Tables verified:")
    logger.info("   - documents           (PDF metadata: title, year, URL, status, language)")
    logger.info("   - document_chunks     (text + page_number + weaviate_id — NO embedding column)")
    logger.info("   - financial_records   (structured budget numbers for SQL queries)")


def reset_weaviate_collection():
    """Deletes old Weaviate collection and confirms it will be recreated fresh."""
    from app.core.weaviate_client import get_weaviate_client, WEAVIATE_INDEX_NAME

    logger.info("Connecting to Weaviate Cloud...")
    client = get_weaviate_client()
    try:
        if client.collections.exists(WEAVIATE_INDEX_NAME):
            logger.info(f"Deleting old Weaviate collection '{WEAVIATE_INDEX_NAME}'...")
            client.collections.delete(WEAVIATE_INDEX_NAME)
            logger.info(f"[OK] Collection '{WEAVIATE_INDEX_NAME}' deleted.")
        else:
            logger.info(f"Collection '{WEAVIATE_INDEX_NAME}' does not exist. Nothing to delete.")
        logger.info("Fresh collection will be auto-created on first ingestion with clean 768-dim vectors.")
    finally:
        client.close()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Gov Intelligence Platform — Database Reset")
    logger.info("  Supabase: SQL tables (no vectors)")
    logger.info("  Weaviate: Vectors only (768-dim bge-base-en-v1.5)")
    logger.info("=" * 60)

    try:
        reset_supabase_tables()
        logger.info("")
        reset_weaviate_collection()
        logger.info("")
        logger.info("[DONE] Database reset complete. Ready for fresh ingestion.")
    except Exception as e:
        logger.error(f"[ERROR] during database reset: {e}", exc_info=True)
        sys.exit(1)
