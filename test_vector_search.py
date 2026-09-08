from app.db.session import SessionLocal
from app.db.models import DocumentChunkModel
from app.ingestion.embedder import embed_texts

def run_test():
    query = "What is the priority for agriculture and capital expenditure in the budget?"
    print(f"\n[QUERY]: {query}")
    
    # 1. Embed query
    query_vector = embed_texts([query])[0]
    
    # 2. Vector search in Supabase PostgreSQL pgvector
    db = SessionLocal()
    results = db.query(DocumentChunkModel).order_by(
        DocumentChunkModel.embedding.cosine_distance(query_vector)
    ).limit(3).all()
    
    print(f"\nTop {len(results)} Vector Search Results from Supabase:")
    print("=" * 60)
    for i, r in enumerate(results, 1):
        print(f"\n[Result #{i}] Document ID: {r.document_id} | Page: {r.page_number}")
        print(r.content[:300].strip() + "...")
        print("-" * 60)
    db.close()

if __name__ == "__main__":
    run_test()
