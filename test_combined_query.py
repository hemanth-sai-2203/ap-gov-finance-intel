from app.core.llm_engine import ask_gov_intel

q = "What was the School Education budget in 2026-27 and compare it with the Health Department allocation?"
print("\n" + "=" * 75)
print("USER QUERY:", q)
print("=" * 75)

res = ask_gov_intel(q, top_k=3)
print("\n--- SYNTHESIZED ANSWER ---")
print(res["answer"])

print("\n--- PROVENANCE CITATIONS ---")
for c in res["citations"]:
    print(f"  • {c['citation_label']}")
print()
