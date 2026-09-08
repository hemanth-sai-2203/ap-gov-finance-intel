import os
from dotenv import load_dotenv
import weaviate
from weaviate.classes.init import Auth
from app.ingestion.embedder import embed_texts

load_dotenv()

def test_weaviate_search():
    url = os.getenv("WEAVIATE_URL")
    api_key = os.getenv("WEAVIATE_API_KEY")
    index_name = os.getenv("WEAVIATE_INDEX_NAME", "GovIntelDocument")

    query = "What is the priority for agriculture and capital expenditure in the budget?"
    print(f"\n[QUERY]: {query}")

    # Generate query vector embedding
    query_vector = embed_texts([query])[0]

    # Connect to Weaviate Cloud
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=url,
        auth_credentials=Auth.api_key(api_key)
    )

    collection = client.collections.get(index_name)
    response = collection.query.near_vector(
        near_vector=query_vector,
        limit=3,
        return_metadata=["distance"]
    )

    print(f"\nTop {len(response.objects)} Vector Results Retrieved DIRECTLY from WEAVIATE CLOUD (10GB):")
    print("=" * 70)
    for i, obj in enumerate(response.objects, 1):
        props = obj.properties
        print(f"\n[Weaviate Result #{i}] Title: {props.get('title')} | Page: {props.get('page_number')} | Year: {props.get('financial_year')}")
        print(f"Content: {props.get('content')[:280].strip()}...")
        print("-" * 70)

    client.close()

if __name__ == "__main__":
    test_weaviate_search()
