import os
import time
import logging
import uuid
from typing import List, Optional
from dotenv import load_dotenv
from langchain_core.documents import Document
from sqlalchemy.orm import Session
import weaviate
from weaviate.classes.init import Auth, AdditionalConfig, Timeout

from app.db.session import SessionLocal
from app.db.models import DocumentModel, DocumentChunkModel
from app.ingestion.embedder import embed_texts
from app.core.weaviate_client import get_weaviate_client, WEAVIATE_INDEX_NAME

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ensure_weaviate_collection(client):
    """
    Ensures the collection exists in Weaviate.
    Collection stores: content + 768-dim bge-base-en-v1.5 vectors + metadata properties.
    """
    if not client.collections.exists(WEAVIATE_INDEX_NAME):
        logger.info(f"Creating Weaviate collection: '{WEAVIATE_INDEX_NAME}'")
        client.collections.create(
            name=WEAVIATE_INDEX_NAME,
            description="AP Government Intelligence Document Chunks — 768-dim bge-base-en-v1.5 vectors"
        )
        logger.info(f"[OK] Collection '{WEAVIATE_INDEX_NAME}' created.")


def delete_document_vectors(collection, document_id: int) -> int:
    """
    Deletes all Weaviate objects belonging to document_id.
    Called before re-uploading to guarantee idempotency — no duplicate vectors
    even if the same document is ingested more than once (e.g. after a crash).
    Returns the number of objects deleted.
    """
    from weaviate.classes.query import Filter
    try:
        result = collection.data.delete_many(
            where=Filter.by_property("document_id").equal(document_id)
        )
        deleted = result.successful if result else 0
        if deleted:
            logger.info(f"[IDEMPOTENCY] Deleted {deleted} stale Weaviate objects for document_id={document_id}.")
        return deleted
    except Exception as e:
        logger.warning(f"Could not delete stale vectors for document_id={document_id}: {e}")
        return 0


def store_document_chunks(
    document_id: int,
    chunks: List[Document],
    db: Optional[Session] = None
) -> int:
    """
    Stores document chunks with resilient connection handling:
    1. Read doc info from Supabase
    2. Generate 768-dim embeddings locally (may take several minutes for large PDFs)
    3. Upload vectors to Weaviate Cloud
    4. Write metadata rows to Supabase SQL using a fresh connection (immune to idle pool timeouts)
    """
    if not chunks:
        logger.warning(f"No chunks to store for document ID {document_id}")
        return 0

    # Step 1: Read doc info with a quick isolated session
    with SessionLocal() as read_session:
        doc_record = read_session.query(DocumentModel).filter(DocumentModel.id == document_id).first()
        if not doc_record:
            raise ValueError(f"Document with ID {document_id} not found in database.")
        title = doc_record.title
        category = doc_record.category
        financial_year = doc_record.financial_year or "N/A"
        language = doc_record.language or "english"

    # Step 2: Extract text content and generate embeddings (CPU intensive)
    chunk_texts = [chunk.page_content for chunk in chunks]
    logger.info(f"Generating 768-dim embeddings for {len(chunk_texts)} chunks of '{title}'...")
    embeddings = embed_texts(chunk_texts)
    logger.info(f"[OK] Embeddings generated.")

    # Step 3: Upload to Weaviate Cloud
    logger.info(f"Uploading {len(chunks)} vectors to Weaviate Cloud...")
    from weaviate.classes.data import DataObject

    chunk_uuids = [str(uuid.uuid4()) for _ in chunks]
    data_objects = []
    for i, (chunk, vector, chunk_uuid) in enumerate(zip(chunks, embeddings, chunk_uuids)):
        # Extract referenced_gos from metadata (list of GO citation strings)
        ref_gos = chunk.metadata.get("referenced_gos", [])
        if isinstance(ref_gos, str):
            ref_gos = [ref_gos] if ref_gos else []
        # Encode as a comma-joined string so Weaviate text filter can search it
        ref_gos_str = " | ".join(ref_gos) if ref_gos else ""

        properties = {
            "document_id":    document_id,
            "supabase_chunk_id": i,
            "title":          title,
            "category":       category,
            "financial_year": financial_year,
            "language":       language,
            "page_number":    int(chunk.metadata.get("page_number", 1)),
            "chunk_index":    i,
            "content":        chunk.page_content,
            "referenced_gos": ref_gos_str,    # searchable cross-doc GO links
            "table_density":  float(chunk.metadata.get("table_density", 0.0)),
        }
        data_objects.append(
            DataObject(
                properties=properties,
                vector=vector,
                uuid=chunk_uuid
            )
        )

    weaviate_client = get_weaviate_client()
    try:
        ensure_weaviate_collection(weaviate_client)
        collection = weaviate_client.collections.get(WEAVIATE_INDEX_NAME)

        # ─── IDEMPOTENCY: wipe any stale vectors for this doc before re-inserting ───
        delete_document_vectors(collection, document_id)

        batch_size = 100
        for start_idx in range(0, len(data_objects), batch_size):
            batch = data_objects[start_idx : start_idx + batch_size]
            collection.data.insert_many(batch)

        logger.info(f"[OK] {len(chunks)} vectors uploaded to Weaviate Cloud ({WEAVIATE_INDEX_NAME}).")
    finally:
        weaviate_client.close()

    # Step 4: Write metadata rows to Supabase SQL using a fresh dedicated session
    with SessionLocal() as write_session:
        try:
            # Clear any old chunks for this document
            write_session.query(DocumentChunkModel).filter(DocumentChunkModel.document_id == document_id).delete()
            write_session.commit()

            # Batch insert chunks in batches of 500
            chunk_records = []
            for i, (chunk, chunk_uuid) in enumerate(zip(chunks, chunk_uuids)):
                page_num = chunk.metadata.get("page_number", 1)
                # Build a clean, typed metadata dict (no str() coercion on lists/booleans)
                ref_gos = chunk.metadata.get("referenced_gos", [])
                meta = {
                    "source_file":    chunk.metadata.get("source_file", ""),
                    "category":       chunk.metadata.get("category", category),
                    "financial_year": chunk.metadata.get("financial_year", financial_year),
                    "is_tabular":     bool(chunk.metadata.get("is_tabular", False)),
                    "table_density":  float(chunk.metadata.get("table_density", 0.0)),
                    "referenced_gos": ref_gos if isinstance(ref_gos, list) else [],
                }

                record = DocumentChunkModel(
                    document_id=document_id,
                    chunk_index=i,
                    page_number=page_num,
                    content=chunk.page_content,
                    weaviate_id=chunk_uuid,
                    chunk_metadata=meta
                )
                chunk_records.append(record)

            # Save in batches to prevent payload overflow
            batch_size = 500
            for start_idx in range(0, len(chunk_records), batch_size):
                write_session.bulk_save_objects(chunk_records[start_idx : start_idx + batch_size])
                write_session.commit()

            # Update document status and chunk count
            live_doc = write_session.query(DocumentModel).filter(DocumentModel.id == document_id).first()
            if live_doc:
                max_page = max([c.metadata.get("page_number", 1) for c in chunks], default=1)
                live_doc.total_pages = max_page
                live_doc.total_chunks = len(chunk_records)
                live_doc.status = "processed"
                write_session.commit()

            logger.info(f"[OK] Stored {len(chunk_records)} chunk metadata rows in Supabase SQL.")
            return len(chunk_records)

        except Exception as e:
            write_session.rollback()
            logger.error(f"Failed writing chunks to Supabase for doc {document_id}: {e}")
            live_doc = write_session.query(DocumentModel).filter(DocumentModel.id == document_id).first()
            if live_doc:
                live_doc.status = "processing_failed"
                write_session.commit()
            raise e
