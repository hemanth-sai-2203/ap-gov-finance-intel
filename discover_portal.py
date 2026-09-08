import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE = "https://apfinance.gov.in"
resp = httpx.get(BASE, verify=False, timeout=10)
soup = BeautifulSoup(resp.content, "html.parser")

print("=== Discovered Portal Navigation Links ===")
seen = set()
for a in soup.find_all("a", href=True):
    href = a["href"].strip()
    text = a.get_text(strip=True)
    full = urljoin(BASE, href)
    if full not in seen and not href.startswith("#") and "javascript" not in href:
        seen.add(full)
        print(f"{text[:40]:<42} -> {full}")
