"""
Mass Ingestion Runner for AP Government Finance Documents.

Discovers, downloads, parses, and embeds official AP Finance budget volumes
directly from official government portal sources into PostgreSQL + pgvector.
"""
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
import urllib.parse
import re

from app.ingestion.downloader import download_document
from app.ingestion.ingest_budget import ingest_pdf_document

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

PORTAL_BUDGET_URL = "https://apfinance.gov.in/budget.html"

async def harvest_official_sources():
    """Extracts all official PDF links from AP Finance Portal."""
    sources = []
    
    # Priority direct 2026-27 / 2025-26 documents
    priority_sources = [
        {
            "title": "AP Budget 2026-27 Guidelines & Estimates",
            "financial_year": "2026-27",
            "document_type": "Guidelines & Estimates",
            "department": "Finance Department",
            "url": "https://apfinance.gov.in/images/BE_2026-27_CBRO_Guidelines.pdf"
        },
        {
            "title": "AP Budget 2026-27 Outreach Programme",
            "financial_year": "2026-27",
            "document_type": "Budget Outreach Memo",
            "department": "Finance Department",
            "url": "https://apfinance.gov.in/images/Budget_Outreach_Programme_2026-27_Circular_Memo.pdf"
        },
        {
            "title": "AP Budget 2024-25 - Vote on Account",
            "financial_year": "2024-25",
            "document_type": "Volume - Vote on Account",
            "department": "Finance Department",
            "url": "https://s3.ap-south-1.amazonaws.com/apfinance.gov.in/uploads/budget-volumes/2024-25/Vote_on_account.pdf"
        },
        {
            "title": "AP Budget 2024-25 - Annexures Volume V (English)",
            "financial_year": "2024-25",
            "document_type": "Volume V - Annexures",
            "department": "Finance Department",
            "url": "https://s3.ap-south-1.amazonaws.com/apfinance.gov.in/uploads/Volume_V_2%202024-25_FinalPrtg.pdf"
        },
        {
            "title": "AP Budget 2023-24 - Budget in Brief (Volume VI)",
            "financial_year": "2023-24",
            "document_type": "Volume VI - Budget in Brief",
            "department": "Finance Department",
            "url": "https://s3.ap-south-1.amazonaws.com/apfinance.gov.in/uploads/budget-volumes/2023-24/ap-budget-in-brief-2023-24-v-6.pdf"
        },
        {
            "title": "AP Budget 2023-24 - Demand XV Education",
            "financial_year": "2023-24",
            "document_type": "Volume III - Education",
            "department": "Education Department",
            "url": "https://s3.ap-south-1.amazonaws.com/apfinance.gov.in/uploads/budget-volumes/2023-24/budget-estimates-2023-24-v-3-12.pdf"
        },
        {
            "title": "AP Budget 2023-24 - Demand XXVII Agriculture",
            "financial_year": "2023-24",
            "document_type": "Volume III - Agriculture",
            "department": "Agriculture Department",
            "url": "https://s3.ap-south-1.amazonaws.com/apfinance.gov.in/uploads/budget-volumes/2023-24/budget-estimates-2023-24-v-3-13.pdf"
        },
        {
            "title": "AP Budget 2023-24 - Demand XVI Health",
            "financial_year": "2023-24",
            "document_type": "Volume III - Health",
            "department": "Health & Family Welfare",
            "url": "https://s3.ap-south-1.amazonaws.com/apfinance.gov.in/uploads/budget-volumes/2023-24/budget-estimates-2023-24-v-3-14.pdf"
        }
    ]
    
    return priority_sources

async def process_mass_ingestion():
    sources = await harvest_official_sources()
    logger.info(f"Starting mass ingestion of {len(sources)} official AP Finance documents...")
    
    successful = 0
    failed = 0
    
    for idx, item in enumerate(sources, 1):
        url = item["url"]
        title = item["title"]
        fy = item["financial_year"]
        doc_type = item["document_type"]
        dept = item["department"]
        
        logger.info(f"\n[{idx}/{len(sources)}] Fetching: {title} ({fy})")
        try:
            meta = await download_document(
                url=url,
                title=title,
                financial_year=fy,
                document_type=doc_type,
                department_name=dept
            )
            
            doc_id = ingest_pdf_document(
                file_path=meta["file_path"],
                title=title,
                financial_year_str=fy,
                document_type=doc_type,
                source_url=url,
                department_name=dept
            )
            logger.info(f"[SUCCESS] Ingested document ID {doc_id}: {title}")
            successful += 1
        except Exception as e:
            logger.error(f"[ERROR] Failed to ingest {title} from {url}: {e}")
            failed += 1
            
    logger.info(f"\n=======================================================")
    logger.info(f"MASS INGESTION SUMMARY: {successful} Succeeded, {failed} Failed.")
    logger.info(f"=======================================================")

if __name__ == "__main__":
    asyncio.run(process_mass_ingestion())
