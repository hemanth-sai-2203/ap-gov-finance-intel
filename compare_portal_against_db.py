import httpx
import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from app.db.session import SessionLocal
from app.db.models import DocumentModel

urllib3.disable_warnings()

PORTAL_SECTIONS = [
    ("Homepage", "https://apfinance.gov.in/"),
    ("Budget Hub", "https://apfinance.gov.in/budget.html"),
    ("Budget Archives", "https://apfinance.gov.in/archieves.html"),
    ("Budget 2026-27", "https://apfinance.gov.in/...Bud@et26-27/"),
    ("Budget Speeches", "https://apfinance.gov.in/budget-speech.html"),
    ("Previous Speeches", "https://apfinance.gov.in/previous.html"),
    ("Finance GOs", "https://apfinance.gov.in/Finance_gos.html"),
    ("GOs Acts & Memos", "https://apfinance.gov.in/go.html"),
    ("FRBM Reports", "https://apfinance.gov.in/frbmreport.html"),
    ("Socio Economic Survey", "https://apfinance.gov.in/socio.html"),
    ("Annual Fiscal Framework", "https://apfinance.gov.in/annual-fiscal.html"),
    ("11th PRC", "https://apfinance.gov.in/11thprc.html"),
    ("State Reorganisation", "https://apfinance.gov.in/state.html"),
    ("Annual Credit Plan", "https://apfinance.gov.in/annual-credit.html"),
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

all_discovered_links = {}

with httpx.Client(headers=headers, verify=False, timeout=12.0, follow_redirects=True) as client:
    for name, url in PORTAL_SECTIONS:
        try:
            resp = client.get(url)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.content, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href or href.startswith("javascript:") or href.startswith("#"):
                    continue
                full_url = urljoin(url, href)
                text = a.get_text(strip=True) or full_url.split("/")[-1]
                
                if ".pdf" in full_url.lower():
                    is_telugu = any(k in full_url.lower() or k in text.lower() for k in ["telugu", "tel_", "_tel", "_te.", "tel.", "-tel"])
                    if not is_telugu and full_url not in all_discovered_links:
                        all_discovered_links[full_url] = {"name": text, "section": name}
        except Exception:
            pass

session = SessionLocal()
db_docs = session.query(DocumentModel).all()
session.close()

db_urls = set()
for d in db_docs:
    if d.source_url:
        db_urls.add(d.source_url.strip().lower())
    if d.title:
        db_urls.add(d.title.strip().lower())

missing_from_db = []
already_in_db = []

for purl, meta in all_discovered_links.items():
    purl_lower = purl.lower()
    filename = purl.split("/")[-1].lower()
    if purl_lower in db_urls or any(filename in u for u in db_urls):
        already_in_db.append((purl, meta))
    else:
        missing_from_db.append((purl, meta))

print(f"=== COMPREHENSIVE PORTAL AUDIT RESULTS ===", flush=True)
print(f"Total Unique English PDFs on Website: {len(all_discovered_links)}", flush=True)
print(f"Total PDFs Present in Ingestion Database: {len(already_in_db)}", flush=True)
print(f"Total PDFs Not in Database: {len(missing_from_db)}", flush=True)

if missing_from_db:
    print("\n--- Unindexed / Missing PDFs Discovered ---", flush=True)
    for idx, (purl, meta) in enumerate(missing_from_db, 1):
        print(f"{idx}. [{meta['section']}] {meta['name']} -> {purl}", flush=True)
else:
    print("\nAll English PDFs across the entire portal are included in the pipeline!", flush=True)
