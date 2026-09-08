"""
Reset & Clean Ingestion State:
1. Wipes Weaviate Cloud 'GovIntelDocument' collection and recreates an empty schema.
2. Clears 'document_chunks' table in Supabase PostgreSQL.
3. Resets 'documents' status to 'downloaded' and total_chunks to 0 (keeps all 912 MB of downloaded PDFs and metadata intact).
"""
import sys
import logging
from app.db.session import SessionLocal
from app.db.models import DocumentModel, DocumentChunkModel
from app.core.weaviate_client import get_weaviate_client, WEAVIATE_INDEX_NAME
from app.ingestion.store import ensure_weaviate_collection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reset_pipeline")

def reset_all():
    logger.info("=======================================================")
    logger.info("STARTING WEAVIATE & SQL CHUNKS CLEAN RESET")
    logger.info("=======================================================")

    # 1. Reset Weaviate
    logger.info("Connecting to Weaviate Cloud...")
    weaviate_client = get_weaviate_client()
    try:
        if weaviate_client.collections.exists(WEAVIATE_INDEX_NAME):
            coll = weaviate_client.collections.get(WEAVIATE_INDEX_NAME)
            try:
                count_before = len(coll)
                logger.info(f"Weaviate collection '{WEAVIATE_INDEX_NAME}' has {count_before} objects before wipe.")
            except Exception as e:
                logger.warning(f"Could not count objects: {e}")
            
            logger.info(f"Deleting collection '{WEAVIATE_INDEX_NAME}' from Weaviate Cloud...")
            weaviate_client.collections.delete(WEAVIATE_INDEX_NAME)
            logger.info(f"[OK] Collection '{WEAVIATE_INDEX_NAME}' deleted.")

        logger.info(f"Recreating clean collection '{WEAVIATE_INDEX_NAME}'...")
        ensure_weaviate_collection(weaviate_client)
        coll = weaviate_client.collections.get(WEAVIATE_INDEX_NAME)
        count_after = len(coll)
        logger.info(f"[OK] Collection '{WEAVIATE_INDEX_NAME}' recreated. Current object count: {count_after}")
    finally:
        weaviate_client.close()

    # 2. Reset Supabase SQL Chunks & Document Status
    logger.info("Connecting to Supabase PostgreSQL...")
    session = SessionLocal()
    try:
        chunks_count_before = session.query(DocumentChunkModel).count()
        docs_count = session.query(DocumentModel).count()
        logger.info(f"Supabase chunks before delete: {chunks_count_before}")
        logger.info(f"Total documents registered: {docs_count}")

        logger.info("Deleting all rows from 'document_chunks' table...")
        session.query(DocumentChunkModel).delete()
        session.commit()
        logger.info("[OK] All chunk rows deleted.")

        logger.info("Resetting document records status...")
        # If local_path exists, mark as 'downloaded', otherwise 'pending'
        docs = session.query(DocumentModel).all()
        for d in docs:
            d.total_chunks = 0
            if d.local_path:
                d.status = "downloaded"
            else:
                d.status = "pending"
        session.commit()
        logger.info(f"[OK] Reset status for {len(docs)} documents to 'downloaded'/'pending'.")

        chunks_count_after = session.query(DocumentChunkModel).count()
        logger.info(f"Supabase chunks after reset: {chunks_count_after}")

    except Exception as e:
        session.rollback()
        logger.error(f"Error resetting SQL database: {e}")
        raise e
    finally:
        session.close()

    logger.info("=======================================================")
    logger.info("[SUCCESS] RESET COMPLETE!")
    logger.info(f"- Weaviate Cloud: Clean empty collection '{WEAVIATE_INDEX_NAME}' (0 objects)")
    logger.info(f"- Supabase SQL:   0 chunks, {docs_count} documents ready for re-ingestion at chunk_size=2000")
    logger.info("=======================================================")

if __name__ == "__main__":
    reset_all()
