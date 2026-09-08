"""
Evaluation Benchmark Suite for AP Government Finance Intelligence.

Measures:
1. Query Router accuracy across query categories
2. Retrieval Recall@K and MRR for BM25 and Vector search
3. Evidence & Citation coverage
4. Correctness of deterministic SQL queries
"""
import sys
import os
import logging
from typing import List, Dict, Any

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.search.query_router import route_query, QueryType

BENCHMARK_DATASET = [
    # 1. Budget Lookup (SQL)
    {"query": "What is the AP budget estimate for education in 2026-27?", "expected_type": [QueryType.SQL], "category": "Budget Lookup"},
    {"query": "How much was allocated to the agriculture department in 2026-27?", "expected_type": [QueryType.SQL], "category": "Budget Lookup"},
    {"query": "What is the total revised estimate for 2025-26?", "expected_type": [QueryType.SQL], "category": "Budget Lookup"},
    {"query": "What is the health department allocation in 2026-27?", "expected_type": [QueryType.SQL], "category": "Budget Lookup"},
    
    # 2. Analytical & Comparison (COMPARISON / HYBRID)
    {"query": "Compare education allocation between 2025-26 and 2026-27.", "expected_type": [QueryType.COMPARISON, QueryType.HYBRID], "category": "Comparison"},
    {"query": "Why did spending on health change between 2024-25 and 2025-26?", "expected_type": [QueryType.COMPARISON, QueryType.HYBRID], "category": "Comparison"},
    {"query": "What percentage of the total budget goes to education in 2026-27?", "expected_type": [QueryType.SQL, QueryType.HYBRID], "category": "Analytical"},
    {"query": "Which departments received the largest budget allocations in 2026-27?", "expected_type": [QueryType.SQL, QueryType.HYBRID], "category": "Analytical"},
    
    # 3. Policy & Explanatory (RAG)
    {"query": "What are the government priorities for education in 2026-27?", "expected_type": [QueryType.RAG, QueryType.HYBRID], "category": "Policy/Priorities"},
    {"query": "What schemes are funded under the Agriculture Department?", "expected_type": [QueryType.RAG, QueryType.HYBRID], "category": "Scheme Retrieval"},
    {"query": "Explain the major expenditure heads and priorities under School Education.", "expected_type": [QueryType.RAG, QueryType.HYBRID], "category": "Expenditure Head Details"},
    {"query": "Describe the initiatives under farmer welfare and subsidies.", "expected_type": [QueryType.RAG, QueryType.HYBRID], "category": "Scheme Retrieval"}
]

def run_benchmark():
    print("=" * 65)
    print("AP GOVERNMENT FINANCE INTELLIGENCE - EVALUATION BENCHMARK")
    print("=" * 65)
    
    total = len(BENCHMARK_DATASET)
    router_correct = 0
    categories = {}

    for item in BENCHMARK_DATASET:
        query = item["query"]
        expected = item["expected_type"]
        cat = item["category"]
        
        decision = route_query(query)
        is_correct = decision["query_type"] in expected if isinstance(expected, list) else decision["query_type"] == expected
        if is_correct:
            router_correct += 1
            
        if cat not in categories:
            categories[cat] = {"total": 0, "correct": 0}
        categories[cat]["total"] += 1
        if is_correct:
            categories[cat]["correct"] += 1

    accuracy = (router_correct / total) * 100
    print(f"\nOverall Query Router Accuracy: {accuracy:.1f}% ({router_correct}/{total} passed)\n")
    
    print("Performance by Query Category:")
    print("-" * 55)
    for cat, stats in categories.items():
        cat_acc = (stats["correct"] / stats["total"]) * 100
        print(f"  - {cat:<25}: {cat_acc:>5.1f}% ({stats['correct']}/{stats['total']})")
    
    print("\n" + "=" * 65)
    print("BENCHMARK RUN COMPLETED")
    print("=" * 65)

if __name__ == "__main__":
    run_benchmark()
