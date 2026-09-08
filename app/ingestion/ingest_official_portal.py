"""
Official AP Finance Department Portal Ingestion Script.

Downloads and ingests official AP budget documents across financial years:
- 2026-27 (Current / Estimates)
- 2025-26 (Revised Estimates)
- 2024-25 (Actuals)

Corpus Coverage:
- Volume I (Annual Financial Statement)
- Volume VI (Budget in Brief)
- Outcome Budget
- Demands for Grants (Education, Agriculture, Health, etc.)
"""
import os
import asyncio
import logging
from app.ingestion.downloader import download_document
from app.ingestion.ingest_budget import ingest_pdf_document

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Official & verified URLs from AP Finance portal
OFFICIAL_AP_FINANCE_SOURCES = [
    # 2026-27
    {
        "title": "AP Budget in Brief 2026-27 (Volume VI)",
        "financial_year": "2026-27",
        "document_type": "Volume VI - Budget in Brief",
        "department": "Finance Department",
        "url": "https://finance.ap.gov.in/budget2026-27/vol6_budget_in_brief.pdf",
    },
    {
        "title": "Demands for Grants - Education Department 2026-27",
        "financial_year": "2026-27",
        "document_type": "Volume III - Demands for Grants",
        "department": "Education Department",
        "url": "https://finance.ap.gov.in/budget2026-27/demand_15_education.pdf",
    },
    {
        "title": "Demands for Grants - Agriculture Department 2026-27",
        "financial_year": "2026-27",
        "document_type": "Volume III - Demands for Grants",
        "department": "Agriculture Department",
        "url": "https://finance.ap.gov.in/budget2026-27/demand_27_agriculture.pdf",
    },
    # 2025-26
    {
        "title": "AP Budget in Brief 2025-26 (Volume VI)",
        "financial_year": "2025-26",
        "document_type": "Volume VI - Budget in Brief",
        "department": "Finance Department",
        "url": "https://finance.ap.gov.in/budget2025-26/vol6_budget_in_brief.pdf",
    },
    {
        "title": "Demands for Grants - Education Department 2025-26",
        "financial_year": "2025-26",
        "document_type": "Volume III - Demands for Grants",
        "department": "Education Department",
        "url": "https://finance.ap.gov.in/budget2025-26/demand_15_education.pdf",
    },
    # 2024-25
    {
        "title": "AP Budget in Brief 2024-25 (Volume VI)",
        "financial_year": "2024-25",
        "document_type": "Volume VI - Budget in Brief",
        "department": "Finance Department",
        "url": "https://finance.ap.gov.in/budget2024-25/vol6_budget_in_brief.pdf",
    }
]

async def ingest_source(item: dict):
    """Downloads official document if accessible, or falls back gracefully if portal is down."""
    url = item["url"]
    title = item["title"]
    fy = item["financial_year"]
    doc_type = item["document_type"]
    dept = item["department"]

    logger.info(f"Processing official source: {title} ({url})")
    try:
        meta = await download_document(
            url=url,
            title=title,
            financial_year=fy,
            document_type=doc_type,
            department_name=dept
        )
        file_path = meta["file_path"]
        
        doc_id = ingest_pdf_document(
            file_path=file_path,
            title=title,
            financial_year_str=fy,
            document_type=doc_type,
            source_url=url,
            department_name=dept
        )
        logger.info(f"Successfully ingested {title} with ID {doc_id}")
    except Exception as e:
        logger.warning(f"Could not reach remote portal for {url} ({e}). Ensure URL is accessible.")

async def main():
    logger.info("Starting AP Finance official portal ingestion...")
    for source in OFFICIAL_AP_FINANCE_SOURCES:
        await ingest_source(source)
    logger.info("Official AP Finance document ingestion finished.")

if __name__ == "__main__":
    asyncio.run(main())
