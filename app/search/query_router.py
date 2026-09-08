"""
Query Router & Entity Extractor Module.

Classifies incoming user questions into optimal retrieval strategies:
  - SQL: Pure numerical / tabular lookup ("What is the total allocation for education in 2026-27?")
  - RAG: Narrative / policy / regulatory questions ("Explain the guidelines for CBRO.")
  - HYBRID: Combined questions ("How much is allocated to Rythu Bharosa and what are its objectives?")
  - COMPARISON: Multi-year analytical queries ("Compare education spending between 2019 and 2026.")

Also extracts key search entities:
  - Financial Years (e.g., '2026-27', '2021', '2019-20')
  - Document Categories ('budget_speech', 'finance_manual', 'guidelines_circulars')
  - Department Hints ('Agriculture', 'Education', 'Finance', 'Health', etc.)
"""
import re
import logging
from enum import Enum
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    SQL = "sql"                 # Deterministic tabular / numeric query
    RAG = "rag"                 # Unstructured semantic / policy text query
    HYBRID = "hybrid"           # Both SQL numbers and RAG narrative needed
    COMPARISON = "comparison"   # Multi-year trend or comparison analysis


# Financial comparison / trend keywords
COMPARISON_KEYWORDS = [
    "compare", "comparison", "versus", "vs", "difference",
    "increase", "decrease", "growth", "trend", "year-over-year",
    "year on year", "yoy", "more than", "less than", "higher",
    "lower", "rose", "fell", "changed"
]

# Explanatory / policy intent keywords
EXPLANATORY_KEYWORDS = [
    "why", "explain", "describe", "priorities", "priority", "focus areas",
    "initiative", "initiatives", "policy", "impact", "benefits", "outcomes",
    "vision", "procedure", "guidelines", "rules", "sanction", "powers",
    "reappropriation", "circular", "process", "eligibility", "objective", "objectives"
]

# Numerical lookup patterns (regex)
NUMERICAL_PATTERNS = [
    r'\bhow much\b',
    r'\bhow many\b',
    r'\btotal\b',
    r'\ballocations?\b',
    r'\ballocated\b',
    r'\bbudgets?\b',
    r'\bexpenditure\b',
    r'\bspending\b',
    r'\bfunding\b',
    r'\bamount\b',
    r'\brupees?\b',
    r'\bcrores?\b',
    r'\blakhs?\b',
    r'\bhead of account\b',
    r'\bmajor head\b',
    r'\bhighest\b',
    r'\blargest\b',
    r'\btop\b',
    r'\bpercentage\b',
    r'\bdeficit\b',
    r'\bgroups?\b'
]

# Year extraction regex (matches '2026-27', '2026', '2019-20', '2019', etc.)
YEAR_RANGE_PATTERN = re.compile(r'\b(20\d{2}[-_]\d{2,4}|20\d{2})\b')

# Department hints
DEPARTMENT_HINTS = {
    "education": "School Education",
    "school": "School Education",
    "agriculture": "Agriculture",
    "farmer": "Agriculture",
    "health": "Health & Family Welfare",
    "medical": "Health & Family Welfare",
    "finance": "Finance",
    "irrigation": "Water Resources",
    "water": "Water Resources",
    "transport": "Transport & R&B",
    "roads": "Transport & R&B",
    "energy": "Energy",
    "power": "Energy",
    "housing": "Housing",
    "welfare": "Social Welfare",
    "revenue": "Revenue",
    "police": "Home / Police",
    "home": "Home / Police",
    "municipal": "Municipal Administration",
    "industry": "Industries & Commerce",
    "industries": "Industries & Commerce"
}

# Category hints
CATEGORY_HINTS = {
    "manual": "finance_manual",
    "rules": "finance_manual",
    "reappropriation": "finance_manual",
    "sanction": "finance_manual",
    "circular": "circulars_memos",
    "circulars": "circulars_memos",
    "guideline": "finance_publication",
    "guidelines": "finance_publication",
    "cbro": "circulars_memos",
    "memo": "circulars_memos",
    "speech": "budget_speech",
    "minister": "budget_speech",
    "frbm": "frbm_report",
    "prc": "prc_report",
    "survey": "socio_economic_survey"
}


def extract_financial_years(query: str) -> List[str]:
    """Extracts all financial years mentioned in the query."""
    matches = YEAR_RANGE_PATTERN.findall(query)
    cleaned = []
    for m in matches:
        m_std = m.replace('_', '-')
        if m_std not in cleaned:
            cleaned.append(m_std)
    return cleaned


def extract_department(query: str) -> Optional[str]:
    """Extracts likely department name from query."""
    q_lower = query.lower()
    for kw, dept_name in DEPARTMENT_HINTS.items():
        if re.search(rf'\b{kw}\b', q_lower):
            return dept_name
    return None


def extract_category(query: str) -> Optional[str]:
    """Extracts category filter if specifically requested."""
    q_lower = query.lower()
    for kw, cat_name in CATEGORY_HINTS.items():
        if re.search(rf'\b{kw}\b', q_lower):
            return cat_name
    return None


def classify_query(query: str) -> QueryType:
    """
    Rule-based query classification.
    Returns: QueryType (SQL | RAG | HYBRID | COMPARISON)
    """
    q_lower = query.lower().strip()

    years = extract_financial_years(query)
    has_numerical = any(re.search(p, q_lower) for p in NUMERICAL_PATTERNS)
    has_comparison = any(kw in q_lower for kw in COMPARISON_KEYWORDS)
    has_explanatory = any(kw in q_lower for kw in EXPLANATORY_KEYWORDS)
    dept = extract_department(query)

    # 1. Multi-year comparison (e.g. "Compare 2019 and 2026" or comparison keywords with year)
    if has_comparison or (len(years) > 1 and has_numerical):
        return QueryType.COMPARISON

    # 2. Hybrid (asks for both numbers and qualitative explanation)
    if has_numerical and has_explanatory:
        return QueryType.HYBRID

    # 3. SQL (clean numerical question with department or year)
    if has_numerical and not has_explanatory:
        return QueryType.SQL

    # 4. Pure narrative / policy / guidelines / rules
    if has_explanatory and not has_numerical:
        return QueryType.RAG

    # 5. Default fallback to HYBRID (retrieves both tabular stats and semantic text)
    return QueryType.HYBRID


def expand_query(query: str) -> List[str]:
    """
    Expands user query by injecting official AP government domain terminology.
    Translates colloquial queries into official terminology to boost BM25 + Vector recall.
    """
    expanded = [query]
    q_lower = query.lower()

    synonym_map = {
        "school": ["School Education Department", "Major Head 2202 General Education"],
        "education": ["School Education", "Higher Education Department"],
        "farmer": ["Agriculture & Allied Sectors", "Rythu Bharosa", "PM-KISAN input subsidy"],
        "agriculture": ["Agriculture Department", "Horticulture", "Price Stabilisation Fund"],
        "health": ["Health, Medical & Family Welfare", "Dr. YSR Aarogyasri healthcare"],
        "medical": ["Health, Medical & Family Welfare Department"],
        "hospital": ["Health & Family Welfare healthcare infrastructure"],
        "roads": ["Transport, Roads & Buildings Department"],
        "cbro": ["Comprehensive Budget Release Order (CBRO) guidelines"],
        "manual": ["A.P. Budget Manual rules and procedures"],
        "reappropriation": ["re-appropriation of budget funds sanction powers"],
        "sanction": ["powers of financial sanction Heads of Departments"],
        "pension": ["Pay Revision Commission (PRC) pension and retirement benefits"],
        "welfare": ["Social Welfare", "Scheduled Castes SC component", "BC component"],
        "housing": ["Housing Department PM Awas Yojana"],
        "metering": ["Prepaid Smart Metering Government Departments billing"]
    }

    terms_added = []
    for trigger, official_terms in synonym_map.items():
        if trigger in q_lower:
            for term in official_terms:
                if term.lower() not in q_lower:
                    terms_added.append(term)

    if terms_added:
        # Create an enriched query variation
        augmented_query = f"{query} ({', '.join(terms_added[:3])})"
        expanded.append(augmented_query)

    return expanded


def route_query(query: str) -> Dict[str, Any]:
    """
    Primary routing function.
    Returns a comprehensive routing decision dict with query expansion.
    """
    q_type = classify_query(query)
    years = extract_financial_years(query)
    department = extract_department(query)
    category = extract_category(query)
    expanded_queries = expand_query(query)

    decision = {
        "original_query": query,
        "expanded_queries": expanded_queries,
        "query_type": q_type,
        "primary_year": years[0] if years else None,
        "all_years": years,
        "department": department,
        "category_filter": category,
        "requires_sql": q_type in [QueryType.SQL, QueryType.HYBRID, QueryType.COMPARISON],
        "requires_vector": True  # Always active as rich knowledge backbone
    }

    logger.info(
        f"Query routed -> Type: {q_type.value} | Years: {years} | Dept: {department} | Cat: {category} | Expanded: {len(expanded_queries)}"
    )
    return decision


if __name__ == "__main__":
    queries = [
        "What is the total budget allocated to School Education in 2026-27?",
        "Explain the guidelines for Comprehensive Budget Release Order CBRO.",
        "Compare agriculture allocation between 2019-20 and 2026-27.",
        "What are the powers of sanction and reappropriation under budget manual?"
    ]
    for q in queries:
        d = route_query(q)
        print(f"\nQ: {q}")
        print(f"  Type: {d['query_type'].value} | Year: {d['primary_year']} | Dept: {d['department']} | Cat: {d['category_filter']}")
