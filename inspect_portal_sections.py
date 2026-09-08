import httpx
import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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
    ("Acts & Rules", "https://apfinance.gov.in/acts-rules.html"),
    ("Manuals", "https://apfinance.gov.in/manuals.html"),
    ("Circulars & Memos", "https://apfinance.gov.in/circulars.html"),
    ("Notifications", "https://apfinance.gov.in/notifications.html"),
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

print("=== EXHAUSTIVE AP FINANCE PORTAL SECTION AUDIT ===", flush=True)

total_pdfs = 0
all_discovered_links = {}

with httpx.Client(headers=headers, verify=False, timeout=12.0, follow_redirects=True) as client:
    for name, url in PORTAL_SECTIONS:
        try:
            resp = client.get(url)
            if resp.status_code != 200:
                print(f"[{name}] HTTP {resp.status_code} at {url}", flush=True)
                continue
            
            soup = BeautifulSoup(resp.content, "html.parser")
            
            # Find all links
            page_pdfs = []
            subpages = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href or href.startswith("javascript:") or href.startswith("#"):
                    continue
                full_url = urljoin(url, href)
                text = a.get_text(strip=True) or full_url.split("/")[-1]
                
                if ".pdf" in full_url.lower():
                    is_telugu = any(k in full_url.lower() or k in text.lower() for k in ["telugu", "tel_", "_tel", "_te.", "tel.", "-tel"])
                    page_pdfs.append((text, full_url, is_telugu))
                    all_discovered_links[full_url] = {"name": text, "section": name, "is_telugu": is_telugu}
                elif "apfinance.gov.in" in full_url and full_url.endswith(".html"):
                    subpages.append((text, full_url))
            
            eng_pdfs = [p for p in page_pdfs if not p[2]]
            tel_pdfs = [p for p in page_pdfs if p[2]]
            print(f"[{name}] Found {len(eng_pdfs)} English PDFs, {len(tel_pdfs)} Telugu PDFs, {len(subpages)} subpage links.", flush=True)
            for text, purl, _ in eng_pdfs[:3]:
                print(f"   - {text[:50]} -> {purl}", flush=True)
            if len(eng_pdfs) > 3:
                print(f"   ... and {len(eng_pdfs) - 3} more English PDFs", flush=True)
            total_pdfs += len(eng_pdfs)
        except Exception as e:
            print(f"[{name}] Error: {e}", flush=True)

print(f"\nTotal English PDF links across all direct portal sections: {total_pdfs}", flush=True)
