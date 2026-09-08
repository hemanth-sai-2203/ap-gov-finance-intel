from app.ingestion.scraper import scrape_pdf_links, CATEGORY_PAGES

for cat in CATEGORY_PAGES.keys():
    docs = scrape_pdf_links(cat)
    print(f"\n=== Category: {cat} (Found {len(docs)} English PDFs) ===")
    for d in docs:
        print(f"  - [{d.get('financial_year')}] {d.get('title')}")
        print(f"    URL: {d.get('source_url')}")
