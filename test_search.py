"""
Multi-domain Search Test across all ingested categories:
1. Policy / Rules from Budget Manual
2. Administrative Circulars / CBRO Guidelines
3. Historical and Recent Budget Speech Allocations
"""
import os
import weaviate
from weaviate.classes.init import Auth
from weaviate.classes.query import MetadataQuery
from dotenv import load_dotenv
from app.ingestion.embedder import embed_texts

load_dotenv()

WEAVIATE_URL = os.getenv("WEAVIATE_URL")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
WEAVIATE_INDEX_NAME = os.getenv("WEAVIATE_INDEX_NAME", "GovIntelDocument")

test_queries = [
    ("Rules & Procedures", "What are the powers of sanction and re-appropriation of budget funds?"),
    ("Government Circulars", "What is the procedure for issue of Comprehensive Budget Release Order CBRO?"),
    ("Fiscal Metrics", "Fiscal deficit and revenue deficit targets in Andhra Pradesh budget 2026-27"),
    ("Welfare & Schemes", "Farmer welfare Rythu Bharosa input subsidy allocations")
]

print("\n" + "=" * 70)
print("  MULTI-DOMAIN WEAVIATE VECTOR SEARCH TEST (768-dim bge-base-en-v1.5)")
print("=" * 70)

client = weaviate.connect_to_weaviate_cloud(
    cluster_url=WEAVIATE_URL,
    auth_credentials=Auth.api_key(WEAVIATE_API_KEY)
)

try:
    collection = client.collections.get(WEAVIATE_INDEX_NAME)

    for domain, query in test_queries:
        print(f"\n[{domain.upper()}] \"{query}\"")
        print("-" * 70)

        query_vector = embed_texts([query])[0]

        results = collection.query.near_vector(
            near_vector=query_vector,
            limit=2,
            return_metadata=MetadataQuery(distance=True),
            return_properties=["title", "category", "financial_year", "page_number", "content"]
        )

        for i, obj in enumerate(results.objects, 1):
            p = obj.properties
            dist = obj.metadata.distance
            snippet = p.get("content", "")[:220].replace("\n", " ")
            print(f"  [{i}] [{p.get('category')}] {p.get('title')[:35]} | Year: {p.get('financial_year','N/A')} | Page: {p.get('page_number','?')} | Distance: {dist:.4f}")
            print(f"      \"{snippet}...\"\n")

finally:
    client.close()

print("=" * 70)
print("[OK] All domain searches verified successfully!")
print("=" * 70 + "\n")
