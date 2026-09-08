"""
SQL Query Engine for Structured Tabular Financial Data Retrieval in Supabase PostgreSQL.

Executes deterministic aggregations (SUM, AVG, GROUP BY, ORDER BY) over `financial_records`.
Guarantees mathematical correctness for exact financial numbers, totals, and year-over-year comparisons.
"""
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import SessionLocal
from app.db.models import FinancialRecordModel, DocumentModel

logger = logging.getLogger(__name__)


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
        query = (
            db.query(FinancialRecordModel, DocumentModel)
            .outerjoin(DocumentModel, FinancialRecordModel.source_document_id == DocumentModel.id)
            .filter(FinancialRecordModel.department.ilike(f"%{department_name}%"))
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


def get_total_budget_by_year(
    financial_year: str,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Computes total budget estimates, revised estimates, and actual expenditure for a given year.
    Uses SQL SUM aggregation.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        res = (
            db.query(
                func.sum(FinancialRecordModel.budget_estimate_cr).label("total_be"),
                func.sum(FinancialRecordModel.revised_estimate_cr).label("total_re"),
                func.sum(FinancialRecordModel.actual_expenditure_cr).label("total_actual")
            )
            .filter(FinancialRecordModel.financial_year == financial_year)
            .first()
        )

        return {
            "financial_year": financial_year,
            "total_budget_estimate_cr": float(res.total_be) if res and res.total_be else 0.0,
            "total_revised_estimate_cr": float(res.total_re) if res and res.total_re else 0.0,
            "total_actual_expenditure_cr": float(res.total_actual) if res and res.total_actual else 0.0,
            "retrieval_method": "sql_aggregation"
        }
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
        rows = (
            db.query(
                FinancialRecordModel.financial_year,
                func.sum(FinancialRecordModel.budget_estimate_cr).label("total_be"),
                func.sum(FinancialRecordModel.revised_estimate_cr).label("total_re"),
                func.sum(FinancialRecordModel.actual_expenditure_cr).label("total_actual")
            )
            .filter(FinancialRecordModel.department.ilike(f"%{department_name}%"))
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
