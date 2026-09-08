import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin

deep_pages = [
    ("Finance GOs", "https://apfinance.gov.in/Finance_gos.html"),
    ("GOs Acts & Memos", "https://apfinance.gov.in/go.html"),
    ("FRBM Reports", "https://apfinance.gov.in/frbmreport.html"),
    ("Socio Economic Survey", "https://apfinance.gov.in/socio.html"),
    ("Annual Fiscal Framework", "https://apfinance.gov.in/annual-fiscal.html"),
    ("11th PRC", "https://apfinance.gov.in/11thprc.html"),
    ("State Reorganisation", "https://apfinance.gov.in/state.html"),
    ("Annual Credit Plan", "https://apfinance.gov.in/annual-credit.html"),
    ("Archives", "https://apfinance.gov.in/archieves.html"),
    ("Budget 2026-27", "https://apfinance.gov.in/...Bud@et26-27/"),
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

total_new_pdfs = 0
print("\n=== DEEP PORTAL SECTION PDF SCAN ===")

for title, url in deep_pages:
    try:
        resp = httpx.get(url, headers=headers, verify=False, timeout=10.0)
        soup = BeautifulSoup(resp.content, "html.parser")
        pdf_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if ".pdf" in href.lower():
                full_pdf = urljoin(url, href)
                raw_text = a.get_text(strip=True)
                # Check telugu
                if not any(k in href.lower() or k in raw_text.lower() for k in ["telugu", "tel_", "_tel"]):
                    pdf_links.append((raw_text or href.split("/")[-1], full_pdf))
        
        print(f"\n[{title}] ({url}) -> Found {len(pdf_links)} English PDFs:")
        for name, link in pdf_links[:4]:
            print(f"   • {name[:50]:<52} -> {link}")
        if len(pdf_links) > 4:
            print(f"   ... and {len(pdf_links)-4} more")
        total_new_pdfs += len(pdf_links)
    except Exception as e:
        print(f"[{title}] Error: {e}")

print(f"\n==========================================")
print(f"TOTAL ADDITIONAL ENGLISH PDFS DISCOVERED: {total_new_pdfs}")
print(f"==========================================\n")
