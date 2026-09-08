import os
import re
import logging
import httpx
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import DocumentModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RAW_PDFS_DIR = os.path.join(os.getcwd(), "data", "raw_pdfs")


import hashlib

def compute_sha256(data: bytes) -> str:
    """Computes SHA-256 hex digest for document bytes."""
    return hashlib.sha256(data).hexdigest()


def sanitize_filename(name: str) -> str:
    """Sanitizes document title into a safe filename."""
    name = re.sub(r'[^a-zA-Z0-9_\- ]', '_', name)
    name = re.sub(r'\s+', '_', name)
    return name.strip('_')[:100]


def download_pdf(
    pdf_info: Dict[str, Any],
    db: Optional[Session] = None
) -> Optional[DocumentModel]:
    """
    Downloads a PDF file to the local directory and registers it in the Supabase documents table.
    
    Args:
        pdf_info: dict with keys: title, category, financial_year, source_url
        db: SQLAlchemy session (optional, will create one if not passed)
        
    Returns:
        DocumentModel instance or None if failed.
    """
    close_db_after = False
    if db is None:
        db = SessionLocal()
        close_db_after = True

    try:
        url = pdf_info["source_url"]
        category = pdf_info.get("category", "uncategorized")
        title = pdf_info.get("title", "Untitled Document")
        year = pdf_info.get("financial_year", "N/A")
        language = pdf_info.get("language", "english")  # Default english; Telugu filtered in scraper

        # Create category folder if it doesn't exist
        category_dir = os.path.join(RAW_PDFS_DIR, category)
        os.makedirs(category_dir, exist_ok=True)

        # Generate safe filename
        safe_title = sanitize_filename(f"{year}_{title}")
        local_filename = f"{safe_title}.pdf"
        local_filepath = os.path.join(category_dir, local_filename)

        # Check if already exists in DB
        doc_record = db.query(DocumentModel).filter(DocumentModel.source_url == url).first()
        if doc_record:
            db.refresh(doc_record)

        if not doc_record:
            doc_record = DocumentModel(
                title=title,
                category=category,
                financial_year=year,
                language=language,
                source_url=url,
                local_path=local_filepath,
                status="pending"
            )
            db.add(doc_record)
            db.commit()
            db.refresh(doc_record)

        # Download file if not already present on disk
        if not os.path.exists(local_filepath) or os.path.getsize(local_filepath) == 0:
            logger.info(f"Downloading: {url} -> {local_filepath}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            resp = httpx.get(url, headers=headers, verify=False, timeout=30, follow_redirects=True)
            resp.raise_for_status()

            with open(local_filepath, "wb") as f:
                f.write(resp.content)

            # Validate PDF magic bytes ("%PDF") — guards against CDN returning
            # an HTML error page with HTTP 200 that gets saved as a .pdf file.
            with open(local_filepath, "rb") as f:
                magic = f.read(4)
            if magic != b"%PDF":
                os.remove(local_filepath)
                logger.warning(
                    f"Downloaded file is not a valid PDF (magic={magic!r}). "
                    f"Deleted corrupt file: {local_filepath}"
                )
                doc_record.status = "download_failed"
                db.commit()
                return None

            file_size_kb = os.path.getsize(local_filepath) / 1024
            logger.info(f"Successfully downloaded '{title}' ({file_size_kb:.1f} KB)")
        else:
            logger.info(f"PDF already exists on disk: {local_filepath}")

        # Update status in DB
        doc_record.local_path = local_filepath
        doc_record.status = "downloaded"
        db.commit()
        db.refresh(doc_record)

        return doc_record

    except Exception as e:
        logger.error(f"Failed to download PDF {pdf_info.get('source_url')}: {e}")
        if db:
            try:
                db.rollback()
            except Exception:
                pass
        if 'doc_record' in locals() and doc_record:
            try:
                doc_record.status = "download_failed"
                db.commit()
            except Exception:
                if db:
                    db.rollback()
        return None
    finally:
        if close_db_after:
            db.close()


if __name__ == "__main__":
    # Test downloader with 1 sample PDF
    sample_pdf = {
        "title": "Speech English 2026-27",
        "category": "budget_speech",
        "financial_year": "2026-27",
        "source_url": "https://apfinance.gov.in/...Bud@et26-27/documents/SpeechEnglish.pdf"
    }
    result = download_pdf(sample_pdf)
    print("Downloaded Doc Record ID:", result.id if result else "Failed")
