import os
import sys
from dotenv import load_dotenv

load_dotenv()

from app.core.query_pipeline import run_query

def main():
    print("=" * 70)
    print("🏛️ AP GOVERNMENT FINANCE INTELLIGENCE - END-TO-END PIPELINE TEST")
    print("=" * 70)

    test_questions = [
        {
            "query": "What are the key priorities and scheme announcements in the 2026-27 Budget Speech?",
            "year": "2026-27",
            "category": "budget_speech"
        },
        {
            "query": "What are the fiscal deficit targets and commitments under the FRBM Act for Andhra Pradesh?",
            "year": None,
            "category": None
        }
    ]

    for i, test in enumerate(test_questions, start=1):
        q = test["query"]
        yr = test["year"]
        cat = test["category"]
        print(f"\n[TEST #{i}] Query: {q}")
        if yr:
            print(f"Filter Year: {yr} | Category: {cat}")
        print("-" * 70)

        try:
            res = run_query(
                query=q,
                financial_year=yr,
                category=cat,
                top_k=4
            )

            print(f"Routing Query Type: {res.get('query_type')}")
            print(f"Retrieved Passages: {res.get('retrieved_passages_count')}")
            print(f"Model Used:         {res.get('model_used')}")
            print("\n📝 GENERATED ANSWER:\n")
            print(res.get("answer"))
            print("\n📄 CITATIONS:")
            citations = res.get("citations", [])
            if citations:
                for c in citations:
                    print(f" - Document: {c.get('document')} | Year: {c.get('financial_year')} | Page: {c.get('page')}")
                    if c.get("excerpt"):
                        print(f"   Excerpt: {c.get('excerpt')[:120]}...")
            else:
                print(" - (No citations extracted)")
            print("=" * 70)

        except Exception as e:
            print(f"❌ Error during query execution: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
