import httpx
from bs4 import BeautifulSoup
import urllib.parse
import re

PORTAL_URLS = [
    "https://apfinance.gov.in",
    "https://budget.ap.gov.in",
    "https://apfinance.gov.in/budget.html"
]

def discover_budget_links():
    found_pdfs = []
    
    with httpx.Client(verify=False, follow_redirects=True, timeout=20.0) as client:
        for portal in PORTAL_URLS:
            try:
                print(f"Scanning {portal}...")
                resp = client.get(portal)
                if resp.status_code != 200:
                    continue
                
                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.find_all("a", href=True)
                
                for a in links:
                    href = a["href"]
                    text = a.get_text(strip=True)
                    
                    if href.lower().endswith(".pdf") or "budget" in href.lower() or "volume" in href.lower() or "demand" in href.lower():
                        full_url = urllib.parse.urljoin(portal, href)
                        found_pdfs.append({
                            "url": full_url,
                            "text": text,
                            "portal": portal
                        })
            except Exception as e:
                print(f"Error scanning {portal}: {e}")
                
    print(f"\nTotal potential PDF/budget links discovered: {len(found_pdfs)}")
    for item in found_pdfs[:15]:
        print(f"  - [{item['text'][:40]}] -> {item['url']}")
        
    return found_pdfs

if __name__ == "__main__":
    discover_budget_links()
