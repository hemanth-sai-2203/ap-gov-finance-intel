import argparse
import logging
import sys
from app.db.session import SessionLocal
from app.db.models import DocumentModel, DocumentChunkModel
from app.ingestion.scraper import scrape_pdf_links, CATEGORY_PAGES
from app.ingestion.downloader import download_pdf
from app.ingestion.loader import load_pdf_document
from app.ingestion.splitter import split_documents
from app.ingestion.store import store_document_chunks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def process_single_pdf(
    pdf_info: dict,
    chunk_size: int = 2000,
    chunk_overlap: int = 400,
    force_reprocess: bool = False,
    db = None
) -> dict:
    """
    Executes the end-to-end ingestion pipeline on a single PDF:
    Scrape -> Download -> LangChain Load -> LangChain Split -> Embed -> Weaviate Vector Store + Supabase SQL.
    Skips if already processed and force_reprocess is False.
    """
    title = pdf_info.get("title", "Untitled")
    url = pdf_info.get("source_url")

    # Step 0: Fast skip check against database
    with SessionLocal() as check_session:
        existing = check_session.query(DocumentModel).filter(DocumentModel.source_url == url).first()
        if not force_reprocess and existing and existing.status == "processed" and (existing.total_chunks or 0) > 0:
            logger.info(f"[SKIP] Already processed: '{title}' ({existing.total_chunks} chunks).")
            return {
                "title": title,
                "document_id": existing.id,
                "status": "already_processed",
                "pages": existing.total_pages,
                "chunks": existing.total_chunks
            }

    # Step 1: Download and register
    doc_record = download_pdf(pdf_info, db=db)
    if not doc_record or not doc_record.local_path:
        logger.error(f"Download step failed for {title}")
        return {"title": title, "status": "download_failed", "chunks": 0}

    # Re-check in case download_pdf refreshed it
    if not force_reprocess and doc_record.status == "processed" and (doc_record.total_chunks or 0) > 0:
        logger.info(f"[SKIP] Already processed: '{title}' ({doc_record.total_chunks} chunks).")
        return {
            "title": title,
            "document_id": doc_record.id,
            "status": "already_processed",
            "pages": doc_record.total_pages,
            "chunks": doc_record.total_chunks
        }

    logger.info(f"\n=======================================================")
    logger.info(f"Processing PDF: '{title}' ({pdf_info.get('financial_year', '')})")
    logger.info(f"Source URL: {url}")
    logger.info(f"=======================================================")

    # Step 2: LangChain Loader
    try:
        pages = load_pdf_document(
            doc_record.local_path,
            doc_metadata={
                "document_id": doc_record.id,
                "title": doc_record.title,
                "category": doc_record.category,
                "financial_year": doc_record.financial_year
            }
        )
    except Exception as e:
        logger.error(f"Loader step failed for {title}: {e}")
        return {"title": title, "status": "load_failed", "chunks": 0}

    # Step 3: LangChain Splitter
    try:
        chunks, tabular_pages = split_documents(
            pages,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        if tabular_pages:
            logger.info(f"[TABLE] {len(tabular_pages)} tabular pages detected in '{title}' — routed to SQL extractor (not chunked).")
    except Exception as e:
        logger.error(f"Splitter step failed for {title}: {e}")
        return {"title": title, "status": "split_failed", "chunks": 0}

    # Step 4: Embed & Store in Weaviate Cloud + Supabase
    try:
        chunk_count = store_document_chunks(doc_record.id, chunks, db=db)
        return {
            "title": title,
            "document_id": doc_record.id,
            "status": "success",
            "pages": len(pages),
            "chunks": chunk_count
        }
    except Exception as e:
        logger.error(f"Store step failed for {title}: {e}")
        return {"title": title, "status": "store_failed", "chunks": 0}


def run_pipeline(
    category: str = "all",
    limit: int = 0,
    chunk_size: int = 2000,
    chunk_overlap: int = 400,
    force_reprocess: bool = False
):
    """
    Runs the comprehensive ingestion pipeline across specified or all categories.
    """
    db = SessionLocal()
    categories_to_run = list(CATEGORY_PAGES.keys()) if category == "all" else [category]

    print(f"\n[STARTING] Comprehensive Gov Intelligence Ingestion Pipeline")
    print(f"   Category: {category} ({len(categories_to_run)} categories)")
    print(f"   Limit per category: {'Unlimited' if limit == 0 else limit}")
    print(f"   Chunk Size: {chunk_size} chars | Overlap: {chunk_overlap} chars\n")

    summary_results = []

    try:
        for cat in categories_to_run:
            print(f"\n>>> Category: {cat}")
            discovered = scrape_pdf_links(cat)

            if not discovered:
                print(f"No PDFs found for category {cat}")
                continue

            # Apply limit if > 0
            selected_docs = discovered[:limit] if limit > 0 else discovered
            print(f"Selected {len(selected_docs)} of {len(discovered)} available PDFs for ingestion.\n")

            for doc_info in selected_docs:
                result = None
                for attempt in range(1, 4):
                    try:
                        result = process_single_pdf(
                            doc_info,
                            chunk_size=chunk_size,
                            chunk_overlap=chunk_overlap,
                            force_reprocess=force_reprocess,
                            db=db
                        )
                        break
                    except Exception as exc:
                        logger.warning(f"Error on doc '{doc_info.get('title')}' (attempt {attempt}/3): {exc}")
                        if attempt < 3:
                            import time
                            time.sleep(5 * attempt)
                        else:
                            result = {"title": doc_info.get("title", "Unknown"), "status": "failed", "chunks": 0}
                if result:
                    summary_results.append(result)

        # Print Final Summary Table
        print("\n" + "=" * 70)
        print(f"{'DOCUMENT TITLE':<40} | {'STATUS':<16} | {'PAGES':<6} | {'CHUNKS':<6}")
        print("=" * 70)
        for r in summary_results:
            title = r["title"][:38]
            status = r.get("status", "unknown")
            pages = str(r.get("pages", 0))
            chunks = str(r.get("chunks", 0))
            print(f"{title:<40} | {status:<16} | {pages:<6} | {chunks:<6}")
        print("=" * 70)

        # Database Stats
        try:
            with SessionLocal() as count_session:
                total_docs = count_session.query(DocumentModel).count()
                processed_docs = count_session.query(DocumentModel).filter(DocumentModel.status == "processed").count()
                total_chunks = count_session.query(DocumentChunkModel).count()
                print(f"\n[STATS] Supabase SQL Records (metadata only, no vectors):")
                print(f"   - Documents Table:       {total_docs} total ({processed_docs} processed)")
                print(f"   - Document Chunks Table: {total_chunks} rows (text + weaviate_id, NO vectors)")
                print(f"   - All 768-dim vectors stored exclusively in Weaviate Cloud")
                print("\n[SUCCESS] Ingestion phase completed successfully!\n")
        except Exception as e:
            logger.warning(f"Could not fetch final stats count: {e}")

    finally:
        try:
            db.close()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AP Gov Intelligence - Document Ingestion Pipeline")
    parser.add_argument(
        "--category",
        type=str,
        default="all",
        choices=list(CATEGORY_PAGES.keys()) + ["all"],
        help="Document category to ingest"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Number of documents to ingest per category (0 = all available)"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=2000,
        help="Max characters per chunk"
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=400,
        help="Overlap characters between chunks"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-processing of already completed documents"
    )

    args = parser.parse_args()
    run_pipeline(
        category=args.category,
        limit=args.limit,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        force_reprocess=args.force
    )
