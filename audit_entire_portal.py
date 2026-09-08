"""
Exhaustive AP Finance Portal PDF Audit Script.
Recursively crawls all navigation menus, archives, and subpages on apfinance.gov.in
to verify whether any English PDF was missed.
"""
import httpx
import re
import urllib3
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from app.db.session import SessionLocal
from app.db.models import DocumentModel

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
    "https://apfinance.gov.in/state.html",
    "https://apfinance.gov.in/annual-credit.html",
    "https://apfinance.gov.in/manuals.html",
    "https://apfinance.gov.in/acts-rules.html",
    "https://apfinance.gov.in/circulars.html",
    "https://apfinance.gov.in/notifications.html",
]

headers = {
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

def run_deep_audit():
    visited_pages = set()
    to_visit = list(START_URLS)
    discovered_pdfs = {}

    client = httpx.Client(headers=headers, verify=False, timeout=12.0, follow_redirects=True)

    print("Starting exhaustive recursive crawl of apfinance.gov.in...")

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
                            "text": link_text,
                            "page_found": curr_url
                        }
                elif is_same_domain(full_url) and full_url not in visited_pages:
                    if full_url not in to_visit:
                        to_visit.append(full_url)
                        
        except Exception as e:
            pass

    client.close()

    print(f"\n=======================================================")
    print(f"Crawl Complete. Visited {len(visited_pages)} HTML pages.")
    print(f"Total Unique PDF URLs Discovered on Site: {len(discovered_pdfs)}")
    print(f"=======================================================\n")

    session = SessionLocal()
    db_docs = session.query(DocumentModel).all()
    session.close()

    db_urls = set()
    for d in db_docs:
        if d.source_url:
            db_urls.add(d.source_url.strip().lower())
    
    telugu_pdfs = []
    indexed_pdfs = []
    missing_pdfs = []

    for pdf_url, info in discovered_pdfs.items():
        url_lower = pdf_url.lower()
        text_lower = info["text"].lower()

        is_telugu = any(k in url_lower or k in text_lower for k in [
            "telugu", "tel_", "_tel", "_te.", "tel.", "telug", "-tel"
        ])
        
        is_indexed = (url_lower in db_urls)
        if not is_indexed:
            filename = pdf_url.split("/")[-1].lower()
            if any(filename in u for u in db_urls):
                is_indexed = True

        if is_telugu:
            telugu_pdfs.append((pdf_url, info))
        elif is_indexed:
            indexed_pdfs.append((pdf_url, info))
        else:
            missing_pdfs.append((pdf_url, info))

    print(f"SUMMARY OF ALL PDFs ON APFINANCE.GOV.IN:")
    print(f"  - English PDFs Already in Database: {len(indexed_pdfs)}")
    print(f"  - Telugu PDFs (Excluded by Policy):  {len(telugu_pdfs)}")
    print(f"  - Unindexed / Missing English PDFs:  {len(missing_pdfs)}")

    if missing_pdfs:
        print("\nUNINDEXED ENGLISH PDFs DISCOVERED:")
        for idx, (m_url, m_info) in enumerate(missing_pdfs, 1):
            print(f"  {idx}. [{m_info['text'][:60]}] -> {m_url} (Found on: {m_info['page_found']})")
    else:
        print("\nPERFECT MATCH! Zero English PDFs were missed on the entire portal!")

if __name__ == "__main__":
    run_deep_audit()
