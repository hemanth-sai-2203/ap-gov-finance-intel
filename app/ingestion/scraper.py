import logging
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://apfinance.gov.in"

CATEGORY_PAGES = {
    "budget_speech": [
        {"url": f"{BASE_URL}/budget-speech.html", "default_year": "2026-27"},
        {"url": f"{BASE_URL}/previous.html", "default_year": "historic"}
    ],
    "budget_volumes": [
        {"url": f"{BASE_URL}/...Bud@et26-27/", "default_year": "2026-27"},
        {"url": f"{BASE_URL}/budget.html", "default_year": "2026-27"}
    ],
    "socio_economic_survey": [
        {"url": f"{BASE_URL}/socio.html", "default_year": "historic"}
    ],
    "frbm_reports": [
        {"url": f"{BASE_URL}/frbmreport.html", "default_year": "historic"}
    ],
    "finance_gos": [
        {"url": f"{BASE_URL}/Finance_gos.html", "default_year": "historic"},
        {"url": f"{BASE_URL}/state.html", "default_year": "historic"}
    ],
    "prc_reports": [
        {"url": f"{BASE_URL}/11thprc.html", "default_year": "reference"}
    ],
    "finance_manual": [
        {"url": f"{BASE_URL}/finance-manuals.html", "default_year": "reference"}
    ],
    "guidelines_circulars": [
        {"url": f"{BASE_URL}/index.html", "default_year": "2026-27"},
        {"url": f"{BASE_URL}/archieves.html", "default_year": "reference"}
    ]
}


def scrape_pdf_links(category: str = "budget_speech") -> List[Dict[str, Any]]:
    """
    Scrapes official PDF links and metadata from apfinance.gov.in for a given category.
    Returns a list of dicts:
        {
            "title": str,
            "category": str,
            "financial_year": str,
            "language": "english",
            "source_url": str
        }
    """
    if category not in CATEGORY_PAGES:
        raise ValueError(f"Unknown category '{category}'. Valid: {list(CATEGORY_PAGES.keys())}")

    pages = CATEGORY_PAGES[category]
    discovered_pdfs = []
    seen_urls = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for page_info in pages:
        page_url = page_info["url"]
        default_year = page_info["default_year"]
        logger.info(f"Scraping category '{category}' from page: {page_url}")

        try:
            resp = httpx.get(page_url, headers=headers, verify=False, timeout=12.0)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].strip()
                if not href or ".pdf" not in href.lower():
                    continue

                full_url = urljoin(page_url, href)
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                raw_text = a_tag.get_text(strip=True)
                filename = full_url.split("/")[-1].replace(".pdf", "").lower()

                # -----------------------------------------------------------------
                # ENGLISH-ONLY FILTER: Skip Telugu and other non-English documents.
                # -----------------------------------------------------------------
                telugu_keywords = ["telugu", "Telugu", "tel_", "_tel", "telugu_", "_telugu"]
                if any(kw.lower() in filename.lower() or kw.lower() in raw_text.lower() for kw in telugu_keywords):
                    logger.info(f"[SKIP] Non-English (Telugu) document filtered out: {filename}")
                    continue

                # Determine clean title
                display_filename = full_url.split("/")[-1].replace(".pdf", "").replace("%20", " ")
                title = raw_text if raw_text and len(raw_text) > 3 and "click" not in raw_text.lower() else display_filename

                # Try to extract financial year from text or URL
                year = default_year
                for possible_year in [
                    "2026-27", "2025-26", "2024-25", "2023-24", "2022-23", "2021-22", "2020-21", 
                    "2019-20", "2018-19", "2017-18", "2016-17", "2015-16", "2014-15", "2013-14", "2012-13", "2011-12",
                    "2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017", "2016", "2015", "2014", "2013", "2012", "2011"
                ]:
                    if possible_year in raw_text or possible_year in full_url:
                        year = possible_year
                        break

                discovered_pdfs.append({
                    "title": title,
                    "category": category,
                    "financial_year": year,
                    "language": "english",
                    "source_url": full_url
                })

        except Exception as e:
            logger.error(f"Error scraping {page_url}: {e}")

    logger.info(f"Discovered {len(discovered_pdfs)} PDFs in category '{category}'")
    return discovered_pdfs


if __name__ == "__main__":
    total = 0
    for cat in CATEGORY_PAGES.keys():
        results = scrape_pdf_links(cat)
        print(f"\n--- Category: {cat} ({len(results)} found) ---")
        for r in results[:2]:
            print(f"  Title: {r['title'][:45]} | Year: {r['financial_year']} | URL: {r['source_url']}")
        total += len(results)
    print(f"\nTotal English PDFs across all categories: {total}")
