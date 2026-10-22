"""
SQL Query Engine for Structured Tabular Financial Data Retrieval in Supabase PostgreSQL.

Executes deterministic aggregations (SUM, AVG, GROUP BY, ORDER BY) over `financial_records`.
Guarantees mathematical correctness for exact financial numbers, totals, and year-over-year comparisons.
"""
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.db.session import SessionLocal
from app.db.models import FinancialRecordModel, DocumentModel

logger = logging.getLogger(__name__)


def get_department_search_terms(department_name: str) -> List[str]:
    """Resolves department aliases to match diverse raw database naming conventions."""
    if not department_name:
        return []
    d_low = department_name.lower().strip()
    if "health" in d_low or "medical" in d_low:
        return ["Health"]
    if "transport" in d_low or "roads" in d_low or "r&b" in d_low:
        return ["Transport", "Roads"]
    if "water" in d_low or "irrigation" in d_low:
        return ["Water Resources", "Irrigation"]
    if "agriculture" in d_low:
        return ["Agriculture"]
    if "municipal" in d_low:
        return ["Municipal"]
    if "panchayat" in d_low or "rural" in d_low:
        return ["Panchayat", "Rural Development"]
    if "higher education" in d_low:
        return ["Higher Education"]
    if "school education" in d_low or ("education" in d_low and "higher" not in d_low):
        return ["School Education", "Education"]
    if "energy" in d_low:
        return ["Energy"]
    if "social welfare" in d_low:
        return ["Social Welfare"]
    if "tribal" in d_low:
        return ["Tribal Welfare"]
    if "minority" in d_low or "minorities" in d_low:
        return ["Minority Welfare", "Minorities"]
    if "bc welfare" in d_low or "backward" in d_low:
        return ["Backward Classes", "Bc Welfare"]
    if "police" in d_low or "home" in d_low:
        return ["Home"]
    return [department_name.strip()]


def get_department_allocation(
    department_name: str,
    financial_year: Optional[str] = None,
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """
    Returns budget allocations for a specific department.
    Optionally filtered by financial year.
    Includes provenance join to DocumentModel.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        search_terms = get_department_search_terms(department_name)
        conds = [FinancialRecordModel.department.ilike(f"%{t}%") for t in search_terms]
        query = (
            db.query(FinancialRecordModel, DocumentModel)
            .outerjoin(DocumentModel, FinancialRecordModel.source_document_id == DocumentModel.id)
            .filter(or_(*conds))
        )
        if financial_year:
            query = query.filter(FinancialRecordModel.financial_year == financial_year)

        rows = query.all()
        results = []
        for record, doc in rows:
            results.append({
                "record_id": record.id,
                "financial_year": record.financial_year,
                "department": record.department,
                "scheme_name": record.scheme_name,
                "head_of_account": record.head_of_account,
                "budget_estimate_cr": float(record.budget_estimate_cr) if record.budget_estimate_cr is not None else None,
                "revised_estimate_cr": float(record.revised_estimate_cr) if record.revised_estimate_cr is not None else None,
                "actual_expenditure_cr": float(record.actual_expenditure_cr) if record.actual_expenditure_cr is not None else None,
                "extra_details": record.extra_details,
                "source_document_title": doc.title if doc else "N/A",
                "source_url": doc.source_url if doc else "N/A",
                "retrieval_method": "sql"
            })
        return results
    finally:
        if close_db:
            db.close()


def get_scheme_allocation(
    scheme_name: str,
    financial_year: Optional[str] = None,
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """
    Returns budget allocations for a specific scheme by matching scheme_name.
    Optionally filtered by financial year.
    Includes provenance join to DocumentModel.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        query = (
            db.query(FinancialRecordModel, DocumentModel)
            .outerjoin(DocumentModel, FinancialRecordModel.source_document_id == DocumentModel.id)
            .filter(
                (FinancialRecordModel.scheme_name.ilike(f"%{scheme_name}%")) |
                (FinancialRecordModel.department.ilike(f"%{scheme_name}%"))
            )
        )
        if financial_year:
            query = query.filter(FinancialRecordModel.financial_year == financial_year)

        rows = query.all()
        results = []
        for record, doc in rows:
            results.append({
                "record_id": record.id,
                "financial_year": record.financial_year,
                "department": record.department,
                "scheme_name": record.scheme_name,
                "head_of_account": record.head_of_account,
                "budget_estimate_cr": float(record.budget_estimate_cr) if record.budget_estimate_cr is not None else None,
                "revised_estimate_cr": float(record.revised_estimate_cr) if record.revised_estimate_cr is not None else None,
                "actual_expenditure_cr": float(record.actual_expenditure_cr) if record.actual_expenditure_cr is not None else None,
                "extra_details": record.extra_details,
                "source_document_title": doc.title if doc else "N/A",
                "source_url": doc.source_url if doc else "N/A",
                "retrieval_method": "sql_scheme"
            })
        return results
    finally:
        if close_db:
            db.close()


def get_total_budget_by_year(
    financial_year: str,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Retrieves the authentic total state budget estimates for a given year.
    Prioritizes official Macro-Fiscal 'Total Budget / Outlay' to avoid double/triple
    counting component figures (Revenue Expenditure + Capital Expenditure + Deficits + Departments).
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # 1. Check for official Total Budget / Outlay row in Macro-Fiscal records
        macro_row = (
            db.query(FinancialRecordModel)
            .filter(
                FinancialRecordModel.financial_year == financial_year,
                FinancialRecordModel.scheme_name.ilike("%Total Budget%")
            )
            .first()
        )
        if macro_row and macro_row.budget_estimate_cr:
            return {
                "financial_year": financial_year,
                "total_budget_estimate_cr": float(macro_row.budget_estimate_cr),
                "total_revised_estimate_cr": float(macro_row.revised_estimate_cr) if macro_row.revised_estimate_cr else 0.0,
                "total_actual_expenditure_cr": float(macro_row.actual_expenditure_cr) if macro_row.actual_expenditure_cr else 0.0,
                "retrieval_method": "sql_official_outlay"
            }

        # 2. Check for Revenue Expenditure + Capital Expenditure sum (Total Outlay = Rev Exp + Cap Exp)
        rev_cap = (
            db.query(
                func.sum(FinancialRecordModel.budget_estimate_cr).label("total_be"),
                func.sum(FinancialRecordModel.revised_estimate_cr).label("total_re"),
                func.sum(FinancialRecordModel.actual_expenditure_cr).label("total_actual")
            )
            .filter(
                FinancialRecordModel.financial_year == financial_year,
                FinancialRecordModel.scheme_name.in_(["Revenue Expenditure", "Capital Expenditure"])
            )
            .first()
        )
        if rev_cap and rev_cap.total_be and rev_cap.total_be > 1000.0:
            return {
                "financial_year": financial_year,
                "total_budget_estimate_cr": float(rev_cap.total_be),
                "total_revised_estimate_cr": float(rev_cap.total_re) if rev_cap.total_re else 0.0,
                "total_actual_expenditure_cr": float(rev_cap.total_actual) if rev_cap.total_actual else 0.0,
                "retrieval_method": "sql_rev_cap_sum"
            }

        # 3. Fallback: Sum distinct departments ONLY, strictly excluding Macro-Fiscal Indicators
        res = (
            db.query(
                func.sum(FinancialRecordModel.budget_estimate_cr).label("total_be"),
                func.sum(FinancialRecordModel.revised_estimate_cr).label("total_re"),
                func.sum(FinancialRecordModel.actual_expenditure_cr).label("total_actual")
            )
            .filter(
                FinancialRecordModel.financial_year == financial_year,
                FinancialRecordModel.department != "Macro-Fiscal Indicators"
            )
            .first()
        )

        return {
            "financial_year": financial_year,
            "total_budget_estimate_cr": float(res.total_be) if res and res.total_be else 0.0,
            "total_revised_estimate_cr": float(res.total_re) if res and res.total_re else 0.0,
            "total_actual_expenditure_cr": float(res.total_actual) if res and res.total_actual else 0.0,
            "retrieval_method": "sql_department_sum"
        }
    finally:
        if close_db:
            db.close()


def get_total_budget_all_years(
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """
    Computes authentic total state budget estimates across all recorded financial years in Supabase SQL.
    Prioritizes official Macro-Fiscal 'Total Budget / Outlay' to avoid double/triple counting.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # 1. Fetch official macro total rows
        macro_rows = (
            db.query(FinancialRecordModel)
            .filter(
                FinancialRecordModel.financial_year.isnot(None),
                FinancialRecordModel.scheme_name.ilike("%Total Budget%")
            )
            .order_by(FinancialRecordModel.financial_year.desc())
            .all()
        )
        found_years = set()
        results = []
        for r in macro_rows:
            if r.financial_year not in found_years and r.budget_estimate_cr:
                found_years.add(r.financial_year)
                results.append({
                    "financial_year": r.financial_year,
                    "budget_estimate_cr": float(r.budget_estimate_cr),
                    "revised_estimate_cr": float(r.revised_estimate_cr) if r.revised_estimate_cr else 0.0,
                    "actual_expenditure_cr": float(r.actual_expenditure_cr) if r.actual_expenditure_cr else 0.0,
                    "source_document_title": f"AP State Annual Financial Statement ({r.financial_year})",
                    "retrieval_method": "sql_official_outlay"
                })

        # 2. For any years without a macro row, sum department allocations excluding Macro-Fiscal Indicators
        dept_rows = (
            db.query(
                FinancialRecordModel.financial_year,
                func.sum(FinancialRecordModel.budget_estimate_cr).label("total_be"),
                func.sum(FinancialRecordModel.revised_estimate_cr).label("total_re"),
                func.sum(FinancialRecordModel.actual_expenditure_cr).label("total_actual")
            )
            .filter(
                FinancialRecordModel.financial_year.isnot(None),
                FinancialRecordModel.department != "Macro-Fiscal Indicators"
            )
            .group_by(FinancialRecordModel.financial_year)
            .order_by(FinancialRecordModel.financial_year.desc())
            .all()
        )
        for yr, be, re, ac in dept_rows:
            if yr not in found_years and be:
                results.append({
                    "financial_year": yr,
                    "budget_estimate_cr": float(be) if be else 0.0,
                    "revised_estimate_cr": float(re) if re else 0.0,
                    "actual_expenditure_cr": float(ac) if ac else 0.0,
                    "source_document_title": f"AP State Annual Financial Statement ({yr})",
                    "retrieval_method": "sql_department_sum"
                })

        return results
    finally:
        if close_db:
            db.close()


def get_top_departments_by_allocation(
    financial_year: str,
    limit: int = 10,
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """
    Returns top N departments ranked by budget estimate allocation for a given year.
    Uses SQL GROUP BY and ORDER BY DESC.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        rows = (
            db.query(
                FinancialRecordModel.department,
                func.sum(FinancialRecordModel.budget_estimate_cr).label("total_be")
            )
            .filter(FinancialRecordModel.financial_year == financial_year)
            .group_by(FinancialRecordModel.department)
            .order_by(func.sum(FinancialRecordModel.budget_estimate_cr).desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "department": dept,
                "financial_year": financial_year,
                "total_budget_estimate_cr": float(be) if be else 0.0,
                "retrieval_method": "sql_aggregation"
            }
            for dept, be in rows
        ]
    finally:
        if close_db:
            db.close()


def compare_department_across_years(
    department_name: str,
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """
    Compares a department's budget allocations across all recorded financial years.
    Returns chronological multi-year summary.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        search_terms = get_department_search_terms(department_name)
        conds = [FinancialRecordModel.department.ilike(f"%{t}%") for t in search_terms]
        rows = (
            db.query(
                FinancialRecordModel.financial_year,
                func.sum(FinancialRecordModel.budget_estimate_cr).label("total_be"),
                func.sum(FinancialRecordModel.revised_estimate_cr).label("total_re"),
                func.sum(FinancialRecordModel.actual_expenditure_cr).label("total_actual")
            )
            .filter(or_(*conds))
            .group_by(FinancialRecordModel.financial_year)
            .order_by(FinancialRecordModel.financial_year.asc())
            .all()
        )

        return [
            {
                "financial_year": yr,
                "department": department_name,
                "budget_estimate_cr": float(be) if be else 0.0,
                "revised_estimate_cr": float(re) if re else 0.0,
                "actual_expenditure_cr": float(ac) if ac else 0.0,
                "retrieval_method": "sql_comparison"
            }
            for yr, be, re, ac in rows
        ]
    finally:
        if close_db:
            db.close()


def get_document_catalog(
    category: Optional[str] = None,
    financial_year: Optional[str] = None,
    limit: int = 50,
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """
    Returns verified document catalog from Postgres SQL metadata.
    Handles meta queries ('what documents do you have?', 'list all budget speeches').
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        query = db.query(DocumentModel).filter(DocumentModel.status.in_(["processed", "downloaded"]))
        if category:
            query = query.filter(DocumentModel.category == category)
        if financial_year:
            query = query.filter(DocumentModel.financial_year == financial_year)

        docs = query.order_by(DocumentModel.financial_year.desc(), DocumentModel.title.asc()).limit(limit).all()
        return [
            {
                "document_id": d.id,
                "title": d.title,
                "category": d.category,
                "financial_year": d.financial_year or "General",
                "total_pages": d.total_pages,
                "source_url": d.source_url,
                "retrieval_method": "sql_catalog"
            }
            for d in docs
        ]
    finally:
        if close_db:
            db.close()

