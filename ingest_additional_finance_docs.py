"""
Dedicated Ingestion Script for 316 Additional AP Finance Department Publications.
Ingests:
- Supplementary Demands & Grant Books (Batch 1 & 2)
- FRBM Compliance & Review Reports
- Socio-Economic Surveys & Fiscal Frameworks
- 10th & 11th Pay Revision Commission (PRC) Volumes
- PMU External Aided Projects (World Bank, ADB, JBIC)
- Finance Department Circular Memos, Treasury Rules & Guidelines
"""
import os
import re
import sys
import glob
import time
import httpx
import logging
import urllib3
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import DocumentModel, DocumentChunkModel
from app.ingestion.loader import load_pdf_document
from app.ingestion.splitter import split_documents
from app.ingestion.store import store_document_chunks

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("additional_finance_ingest")

SAVE_DIR = "data/raw_pdfs/additional_finance_docs"
os.makedirs(SAVE_DIR, exist_ok=True)

# ─── Financial year extractor ─────────────────────────────────────────────────
# Ordered longest-match first so "2026-27" beats "2026".
_YEAR_RANGE = re.compile(r'20(1[1-9]|2[0-9])[-–/](1[2-9]|2[0-9]|[3-9][0-9])')
_YEAR_SINGLE = re.compile(r'\b(20(?:1[1-9]|2[0-9]))\b')
# PRC ordinal labels → approximate fiscal year of commission
_PRC_YEAR = {
    "11th": "2015-16", "11": "2015-16",
    "10th": "2010-11", "10": "2010-11",
    "9th":  "2005-06",  "9": "2005-06",
}

def extract_financial_year(title: str, url: str) -> str:
    """
    Extracts the most likely fiscal year label from a document title + URL.
    Falls back to 'General' only when nothing can be inferred.
    """
    combined = f"{title} {url}"

    # 1. Prefer full fiscal-year range like "2024-25"
    m = _YEAR_RANGE.search(combined)
    if m:
        return m.group(0)

    # 2. PRC ordinal in title/URL
    for token, fy in _PRC_YEAR.items():
        if re.search(rf'\b{token}\b', combined, re.IGNORECASE):
            return fy

    # 3. Fall back to single calendar year
    m = _YEAR_SINGLE.search(combined)
    if m:
        year = int(m.group(1))
        return f"{year}-{str(year+1)[2:]}"   # e.g. 2015 → "2015-16"

    return "General"

BASE_DOMAIN = "apfinance.gov.in"
START_URLS = [
    "https://apfinance.gov.in/",
    "https://apfinance.gov.in/index.html",
    "https://apfinance.gov.in/budget.html",
    "https://apfinance.gov.in/archieves.html",
    "https://apfinance.gov.in/Finance_gos.html",
    "https://apfinance.gov.in/go.html",
    "https://apfinance.gov.in/frbmreport.html",
    "https://apfinance.gov.in/socio.html",
    "https://apfinance.gov.in/annual-fiscal.html",
    "https://apfinance.gov.in/11thprc.html",
    "https://apfinance.gov.in/10th-prc.html",
    "https://apfinance.gov.in/9th-prc.html",
    "https://apfinance.gov.in/state.html",
    "https://apfinance.gov.in/annual-credit.html",
    "https://apfinance.gov.in/manuals.html",
    "https://apfinance.gov.in/acts-rules.html",
    "https://apfinance.gov.in/circulars.html",
    "https://apfinance.gov.in/notifications.html",
    "https://apfinance.gov.in/pmu.html",
    "https://apfinance.gov.in/statecommission.html",
    "https://apfinance.gov.in/more.html",
    "https://apfinance.gov.in/achievements.html",
    "https://apfinance.gov.in/finance-manuals.html",
    "https://apfinance.gov.in/rti.html"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def is_same_domain(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return BASE_DOMAIN in parsed.netloc
    except Exception:
        return False

def clean_url(url: str) -> str:
    return url.split("#")[0].strip()

def sanitize_filename(name: str) -> str:
    clean = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name)
    clean = re.sub(r'_+', '_', clean)
    return clean[:100]

def discover_additional_urls():
    """Runs an exhaustive recursive crawl of apfinance.gov.in to discover all unindexed PDFs."""
    visited_pages = set()
    to_visit = list(START_URLS)
    discovered_pdfs = {}

    client = httpx.Client(headers=HEADERS, verify=False, timeout=12.0, follow_redirects=True)
    logger.info("Discovering all PDFs on apfinance.gov.in...")

    while to_visit:
        curr_url = to_visit.pop(0)
        curr_url = clean_url(curr_url)
        if curr_url in visited_pages or not is_same_domain(curr_url):
            continue
        
        visited_pages.add(curr_url)
        if any(curr_url.lower().endswith(ext) for ext in [".pdf", ".zip", ".jpg", ".png", ".xlsx", ".docx"]):
            continue

        try:
            resp = client.get(curr_url)
            if resp.status_code != 200:
                continue
            
            soup = BeautifulSoup(resp.content, "html.parser")
            for a in soup.find_all("a", href=True):
                raw_href = a["href"].strip()
                if not raw_href or raw_href.startswith("javascript:") or raw_href.startswith("mailto:") or raw_href.startswith("tel:"):
                    continue
                
                full_url = urljoin(curr_url, raw_href)
                full_url = clean_url(full_url)
                
                if ".pdf" in full_url.lower():
                    link_text = a.get_text(strip=True) or full_url.split("/")[-1]
                    if full_url not in discovered_pdfs:
                        discovered_pdfs[full_url] = {
                            "title": link_text,
                            "source_page": curr_url
                        }
                elif is_same_domain(full_url) and full_url not in visited_pages:
                    if full_url not in to_visit:
                        to_visit.append(full_url)
        except Exception:
            pass

    client.close()
    logger.info(f"Crawl complete. Visited {len(visited_pages)} pages. Total unique PDFs found: {len(discovered_pdfs)}")

    # Check against database
    session = SessionLocal()
    existing_docs = session.query(DocumentModel).all()
    session.close()

    existing_urls = {d.source_url.strip().lower() for d in existing_docs if d.source_url}
    
    targets = []
    for url, meta in discovered_pdfs.items():
        url_lower = url.lower()
        title_lower = meta["title"].lower()

        # Skip Telugu
        if any(k in url_lower or k in title_lower for k in ["telugu", "tel_", "_tel", "_te.", "tel.", "telug", "-tel"]):
            continue
        
        # Check if already indexed
        if url_lower in existing_urls:
            continue
        
        # Check if filename already in existing_urls
        filename = url_lower.split("/")[-1]
        if any(filename in u for u in existing_urls):
            continue

        # Infer category
        category = "finance_publication"
        if "prc" in url_lower or "prc" in title_lower:
            category = "prc_report"
        elif "frbm" in url_lower or "frbm" in title_lower:
            category = "frbm_report"
        elif "socio" in url_lower or "survey" in title_lower:
            category = "socio_economic_survey"
        elif "suppl" in url_lower or "further" in title_lower or "grant" in title_lower:
            category = "supplementary_demands"
        elif "pmu" in url_lower or "world" in url_lower or "jbic" in url_lower or "adb" in url_lower:
            category = "external_aided_projects"
        elif "circular" in url_lower or "memo" in url_lower or "guideline" in url_lower:
            category = "circulars_memos"

        targets.append({
            "url": url,
            "title": meta["title"][:200],
            "category": category
        })

    logger.info(f"Targeting {len(targets)} unindexed English publications for ingestion.")
    return targets

def download_pdf(url: str, title: str, index: int, total: int) -> str:
    filename = f"{index:03d}_{sanitize_filename(title)}.pdf"
    local_path = os.path.join(SAVE_DIR, filename)

    # If file exists on disk, verify it is a real PDF (not a cached HTML error page)
    if os.path.exists(local_path) and os.path.getsize(local_path) > 1024:
        with open(local_path, "rb") as f:
            magic = f.read(4)
        if magic == b"%PDF":
            return local_path
        else:
            logger.warning(f"Cached file is not a valid PDF (magic={magic!r}), re-downloading: {local_path}")
            os.remove(local_path)

    logger.info(f"[{index}/{total}] Downloading: '{title[:60]}' from {url}")
    try:
        with httpx.Client(headers=HEADERS, verify=False, timeout=30.0, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200 and len(resp.content) > 500:
                # Validate magic bytes before writing
                if resp.content[:4] != b"%PDF":
                    logger.warning(f"Response is not a valid PDF (magic={resp.content[:4]!r}), skipping: {url}")
                    return None
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                return local_path
            else:
                logger.warning(f"Failed to download {url} (HTTP {resp.status_code})")
                return None
    except Exception as e:
        logger.warning(f"Error downloading {url}: {e}")
        return None


def ingest_all_additional():
    targets = discover_additional_urls()
    total = len(targets)
    logger.info(f"Starting ingestion of {total} additional finance publications...")

    success_count = 0
    skipped_count = 0

    for idx, item in enumerate(targets, 1):
        url = item["url"]
        title = item["title"]
        category = item["category"]
        financial_year = extract_financial_year(title, url)

        logger.info(f"\n=======================================================")
        logger.info(f"[{idx}/{total}] Processing: '{title}' ({category})")
        logger.info(f"URL: {url}")
        logger.info(f"=======================================================")

        local_path = download_pdf(url, title, idx, total)
        if not local_path:
            skipped_count += 1
            continue

        try:
            # 1. Check/create document row in Supabase
            session = SessionLocal()
            doc_rec = session.query(DocumentModel).filter(DocumentModel.source_url == url).first()
            if not doc_rec:
                doc_rec = DocumentModel(
                    title=title,
                    category=category,
                    financial_year=financial_year,
                    language="english",
                    source_url=url,
                    local_path=local_path,
                    status="pending"
                )
                session.add(doc_rec)
                session.commit()
                session.refresh(doc_rec)
            elif doc_rec.financial_year in (None, "General"):
                # Backfill year if previously defaulted to General
                doc_rec.financial_year = financial_year
                session.commit()
            doc_id = doc_rec.id
            session.close()

            # 2. Load pages with PyMuPDF & clean Telugu
            pages = load_pdf_document(local_path, doc_metadata={
                "title": title,
                "category": category,
                "financial_year": financial_year,
                "doc_id": doc_id
            })

            if not pages:
                logger.warning(f"All pages were Telugu/scanned for '{title}'. Skipping.")
                skipped_count += 1
                continue

            # 3. Chunk text (tabular pages are separated out, not embedded)
            chunks, tabular_pages = split_documents(pages, chunk_size=2000, chunk_overlap=400)
            if tabular_pages:
                logger.info(f"[TABLE] {len(tabular_pages)} tabular pages separated from '{title}' — will go to SQL extractor.")
            if not chunks:
                logger.warning(f"No chunks generated for '{title}'. Skipping.")
                skipped_count += 1
                continue

            logger.info(f"Generated {len(chunks)} clean text chunks from {len(pages)} pages.")

            # 4. Generate embeddings and store in Weaviate + Supabase
            stored_count = store_document_chunks(doc_id, chunks)

            # 5. Mark processed
            session = SessionLocal()
            doc_obj = session.query(DocumentModel).filter(DocumentModel.id == doc_id).first()
            if doc_obj:
                doc_obj.total_pages = len(pages)
                doc_obj.total_chunks = stored_count
                doc_obj.status = "processed"
                session.commit()
            session.close()

            success_count += 1
            logger.info(f"[SUCCESS] Ingested '{title}' ({stored_count} chunks). Progress: {success_count}/{total}")

        except Exception as e:
            logger.error(f"Failed processing '{title}': {e}", exc_info=True)
            skipped_count += 1

    logger.info(f"\n=======================================================")
    logger.info(f"ALL ADDITIONAL FINANCE PUBLICATIONS COMPLETE!")
    logger.info(f"Successfully Ingested: {success_count} | Skipped: {skipped_count} | Total: {total}")
    logger.info(f"=======================================================\n")

if __name__ == "__main__":
    ingest_all_additional()
