import os
from app.db.session import SessionLocal
from app.db.models import FinancialRecordModel
from app.search.sql_engine import (
    get_department_allocation,
    get_total_budget_by_year,
    get_top_departments_by_allocation,
    compare_department_across_years
)

db = SessionLocal()

print("\n" + "=" * 70)
print("  STRUCTURED FINANCIAL SQL ENGINE VERIFICATION (220 RECORDS)")
print("=" * 70)

# 1. Check Total Records
total = db.query(FinancialRecordModel).count()
print(f"\n1. Total Records in Supabase SQL: {total}")

# 2. Top Departments for 2026-27
print("\n2. Top Department Allocations for 2026-27 (SQL GROUP BY + ORDER BY):")
top_2026 = get_top_departments_by_allocation("2026-27", limit=6, db=db)
for idx, d in enumerate(top_2026, 1):
    print(f"   [{idx}] {d['department']}: Rs. {d['total_budget_estimate_cr']:,.2f} Crore")

# 3. Specific Department Lookup
print("\n3. School Education Department Allocation in 2026-27 (Exact SQL Lookup):")
edu = get_department_allocation("School Education", financial_year="2026-27", db=db)
for e in edu:
    print(f"   Department: {e['department']} | Amount: Rs. {e['budget_estimate_cr']:,.2f} Crore | Scheme: {e['scheme_name']}")

# 4. Multi-Year Comparison across 15 Years
print("\n4. Health Department Multi-Year Budget Trend (SQL Chronological Comparison):")
health_trend = compare_department_across_years("Health", db=db)
for h in health_trend:
    print(f"   FY {h['financial_year']:<10} -> Rs. {h['budget_estimate_cr']:>10,.2f} Crore")

# 5. Macro-Fiscal Deficit Lookup
print("\n5. Macro-Fiscal Deficit Indicators in 2026-27:")
deficits = get_department_allocation("Macro-Fiscal", financial_year="2026-27", db=db)
for df in deficits:
    print(f"   {df['scheme_name']:<25}: Rs. {df['budget_estimate_cr']:>10,.2f} Crore")

db.close()
print("\n" + "=" * 70)
print("[SQL DATA EXTRACTION & VERIFICATION COMPLETE!]")
print("=" * 70 + "\n")
