"""
Structured Financial Tabular Data Extractor for AP Government Budgets.

Extracts deterministic financial figures directly from official budget documents:
  - Department-wise Budget Allocations (in Rs. Crores)
  - Flagship Welfare Scheme Allocations (in Rs. Crores)
  - Macro-Fiscal Indicators (Revenue Deficit, Fiscal Deficit, Revenue Expenditure, Capital Expenditure)

Populates Supabase PostgreSQL's `financial_records` table for zero-hallucination deterministic SQL queries.
"""
import os
import re
import logging
from typing import List, Dict, Any, Optional
import pymupdf
from sqlalchemy.orm import Session
from app.core.config import settings

from app.db.session import SessionLocal
from app.db.models import DocumentModel, FinancialRecordModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Regular expressions for departmental allocation pattern matching
DEPARTMENT_ALLOCATION_PATTERNS = [
    # Pattern 1: "Rs. X crore for Department / to the Department"
    re.compile(r'(?:Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr)\s*(?:for|to|towards)?\s*(?:the)?\s*([A-Za-z0-9&,\-\s]{3,60}?)\s*(?:Department|Sector|component|scheme)', re.IGNORECASE),
    # Pattern 2: "allocate/propose Rs. X crore to/for Department"
    re.compile(r'(?:allocate|propose|allocating|proposing)\s*(?:an\s*allocation\s*of)?\s*(?:Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr)\s*(?:for|to|towards)?\s*(?:the)?\s*([A-Za-z0-9&,\-\s]{3,60}?)\s*(?:Department|Sector|component)?(?:\s*for\s*(?:FY|the\s*year)?\s*[\d\-]+)?', re.IGNORECASE),
    # Pattern 3: "DepartmentName ... Rs. X crore"
    re.compile(r'([A-Za-z0-9&,\-\s]{4,50}?)\s*(?:Department|Sector|component)?\s*:\s*(?:Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr)', re.IGNORECASE),
]

# Macro indicators patterns
MACRO_PATTERNS = [
    ("Revenue Deficit", re.compile(r'revenue\s*deficit\s*(?:of|is|around)?\s*(?:Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr)', re.IGNORECASE)),
    ("Fiscal Deficit", re.compile(r'fiscal\s*deficit\s*(?:of|is|around)?\s*(?:Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr)', re.IGNORECASE)),
    ("Revenue Expenditure", re.compile(r'revenue\s*expenditure\s*(?:for\s*[^,\.]*)?(?:of|is|around|estimated\s*at)?\s*(?:Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr)', re.IGNORECASE)),
    ("Capital Expenditure", re.compile(r'capital\s*expenditure\s*(?:for\s*[^,\.]*)?(?:of|is|around|estimated\s*at)?\s*(?:Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr)', re.IGNORECASE)),
    ("Total Budget / Outlay", re.compile(r'(?:total\s*budget|budget\s*outlay|total\s*expenditure)\s*(?:of|is|around)?\s*(?:Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr)', re.IGNORECASE)),
]

KNOWN_DEPARTMENTS = [
    "School Education", "Higher Education", "Health, Medical & Family Welfare", "Health",
    "Agriculture", "Agriculture & Allied Sectors", "Horticulture", "Animal Husbandry", "Fisheries",
    "Panchayat Raj & Rural Development", "Panchayat Raj", "Rural Development",
    "Municipal Administration & Urban Development", "Municipal Administration",
    "Water Resources", "Irrigation", "Transport, Roads & Buildings", "Transport", "Roads & Buildings",
    "Energy", "Housing", "Social Welfare", "Scheduled Castes (SC) Component", "Tribal Welfare", "ST Component",
    "Backward Classes (BC) Welfare", "BC Component", "Minorities Welfare", "Minority Welfare",
    "Women & Child Welfare", "Women, Children, Differently Abled and Senior Citizens",
    "Industries & Commerce", "Information Technology, Electronics & Communications", "IT & Electronics",
    "Infrastructure & Investments", "Home / Police", "Home Department", "Law & Justice", "Judiciary",
    "Prohibition & Excise", "Forest, Environment, Science & Technology", "Tourism, Culture & Youth",
    "Labour, Employment, Training & Factories", "Labour", "Skill Development & Entrepreneurship",
    "Civil Supplies / Consumer Affairs", "Food & Civil Supplies", "Revenue Department"
]


def clean_number(num_str: str) -> Optional[float]:
    """Converts a formatted number string like '32,308.50' into a float."""
    try:
        cleaned = num_str.replace(',', '').strip()
        return float(cleaned)
    except Exception:
        return None


def clean_department_name(raw_dept: str) -> str:
    """Standardizes department string."""
    cleaned = raw_dept.strip(' :,-.\n\t')
    cleaned = re.sub(r'^(the|an|a)\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+Department$', '', cleaned, flags=re.IGNORECASE)
    
    # Match against known canonical names
    for known in KNOWN_DEPARTMENTS:
        if known.lower() in cleaned.lower() or cleaned.lower() in known.lower():
            return known
            
    return cleaned.title()


def extract_financial_data_from_pdf(
    pdf_path: str,
    financial_year: str,
    document_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Extracts structured financial allocations and macro figures from a budget speech PDF.
    """
    if not os.path.exists(pdf_path):
        logger.warning(f"File not found: {pdf_path}")
        return []

    records = []
    seen_keys = set()

    doc = pymupdf.open(pdf_path)
    logger.info(f"Extracting financial records from {os.path.basename(pdf_path)} ({len(doc)} pages)...")

    for page_num in range(len(doc)):
        text = doc[page_num].get_text()
        page_idx = page_num + 1

        # 1. Extract Macro Indicators (Deficits, Outlays)
        for indicator_name, pattern in MACRO_PATTERNS:
            for match in pattern.finditer(text):
                amt_str = match.group(1)
                amount = clean_number(amt_str)
                if amount and amount > 10.0:  # Ignore trivial numbers
                    key = (financial_year, "Macro-Fiscal", indicator_name)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        records.append({
                            "financial_year": financial_year,
                            "department": "Macro-Fiscal Indicators",
                            "scheme_name": indicator_name,
                            "budget_estimate_cr": amount,
                            "revised_estimate_cr": None,
                            "actual_expenditure_cr": None,
                            "source_document_id": document_id,
                            "extra_details": {
                                "source_page": page_idx,
                                "matched_text": match.group(0).strip(),
                                "type": "macro_fiscal"
                            }
                        })

        # 2. Extract Department Allocations
        # Method A: Pattern regex matching
        for pattern in DEPARTMENT_ALLOCATION_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groups()
                if len(groups) == 2:
                    # Determine which group is amount and which is department
                    if any(c.isdigit() for c in groups[0]):
                        amt_str, dept_raw = groups[0], groups[1]
                    else:
                        dept_raw, amt_str = groups[0], groups[1]

                    amount = clean_number(amt_str)
                    dept_name = clean_department_name(dept_raw)

                    # Validate amount and department name
                    if amount and amount > 5.0 and len(dept_name) > 3 and not dept_name.isdigit():
                        if any(stop in dept_name.lower() for stop in ["year", "crore", "lakh", "above", "below", "following"]):
                            continue

                        key = (financial_year, dept_name, "Department Allocation")
                        if key not in seen_keys:
                            seen_keys.add(key)
                            records.append({
                                "financial_year": financial_year,
                                "department": dept_name,
                                "scheme_name": "General Departmental Allocation",
                                "budget_estimate_cr": amount,
                                "revised_estimate_cr": None,
                                "actual_expenditure_cr": None,
                                "source_document_id": document_id,
                                "extra_details": {
                                    "source_page": page_idx,
                                    "matched_text": match.group(0).strip(),
                                    "type": "department_allocation"
                                }
                            })

        # Method B: Direct Scan for Known Departments on the page
        for dept in KNOWN_DEPARTMENTS:
            dept_pattern = re.compile(
                rf'{re.escape(dept)}[^\.\n]{{0,60}}?(?:Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|cr)',
                re.IGNORECASE
            )
            for m in dept_pattern.finditer(text):
                amount = clean_number(m.group(1))
                if amount and amount > 5.0:
                    key = (financial_year, dept, "Department Allocation")
                    if key not in seen_keys:
                        seen_keys.add(key)
                        records.append({
                            "financial_year": financial_year,
                            "department": dept,
                            "scheme_name": "General Departmental Allocation",
                            "budget_estimate_cr": amount,
                            "revised_estimate_cr": None,
                            "actual_expenditure_cr": None,
                            "source_document_id": document_id,
                            "extra_details": {
                                "source_page": page_idx,
                                "matched_text": m.group(0).strip(),
                                "type": "department_scan"
                            }
                        })

    doc.close()
    logger.info(f"[OK] Extracted {len(records)} structured financial records for FY {financial_year}.")
    return records


def run_full_financial_extraction(db: Optional[Session] = None) -> int:
    """
    Extracts and stores structured financial records across all ingested documents.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    total_inserted = 0

    try:
        # Get all budget speech documents from database
        docs = db.query(DocumentModel).filter(DocumentModel.category == "budget_speech").all()
        logger.info(f"Found {len(docs)} budget speech documents in database for structured extraction.")

        # Clear existing records to allow clean idempotency
        db.query(FinancialRecordModel).delete()
        db.commit()
        logger.info("Cleared existing financial_records table.")

        for doc in docs:
            if not doc.local_path or not os.path.exists(doc.local_path):
                continue

            records = extract_financial_data_from_pdf(
                pdf_path=doc.local_path,
                financial_year=doc.financial_year or "N/A",
                document_id=doc.id
            )

            # Insert into database
            db_objects = [
                FinancialRecordModel(
                    financial_year=r["financial_year"],
                    department=r["department"],
                    scheme_name=r["scheme_name"],
                    budget_estimate_cr=r["budget_estimate_cr"],
                    revised_estimate_cr=r["revised_estimate_cr"],
                    actual_expenditure_cr=r["actual_expenditure_cr"],
                    source_document_id=r["source_document_id"],
                    extra_details=r["extra_details"]
                )
                for r in records
            ]

            if db_objects:
                db.bulk_save_objects(db_objects)
                db.commit()
                total_inserted += len(db_objects)

        logger.info(f"\n[DONE] Successfully inserted {total_inserted} structured financial records into Supabase SQL!")
        return total_inserted

    except Exception as e:
        db.rollback()
        logger.error(f"Failed during financial extraction: {e}", exc_info=True)
        raise e
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    count = run_full_financial_extraction()
    print(f"\nTotal Financial Records Populated: {count}")
