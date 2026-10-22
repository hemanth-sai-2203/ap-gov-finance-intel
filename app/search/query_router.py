"""
Query Router & Entity Extractor Module for AP Government Finance Intelligence.

Classifies incoming user questions into optimal retrieval strategies:
  - GREETING: Conversational greetings, introductory queries ("hello", "hi", "help")
  - SQL: Pure numerical / tabular lookup ("What is the total allocation for education in 2026-27?")
  - RAG: Narrative / policy / regulatory questions ("Explain the guidelines for CBRO.")
  - HYBRID: Combined questions ("How much is allocated to Rythu Bharosa and what are its objectives?")
  - COMPARISON: Multi-year analytical queries ("Compare education spending between 2019 and 2026.")
  - CATALOG: Meta / document listing queries ("list all budget speeches", "what documents exist")

Includes:
  - Natural Language Normalizer & Typo Fixer (e.g. '2024-15Budget' -> '2024-25 Budget')
  - AI Query Restructurer (Hugging Face / Gemini Inference with local rule fallback)
  - Domain Synonym Expansion for BM25 and Vector Search
"""
import re
import json
import logging
from enum import Enum
from typing import Optional, Dict, Any, List
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    GREETING = "greeting"       # Direct conversational greeting / help intent
    SQL = "sql"                 # Deterministic tabular / numeric query
    RAG = "rag"                 # Unstructured semantic / policy text query
    HYBRID = "hybrid"           # Both SQL numbers and RAG narrative needed
    COMPARISON = "comparison"   # Multi-year trend or comparison analysis
    CATALOG = "catalog"         # Meta / document listing query ("list all budget speeches")


# Greeting & conversational patterns
GREETING_PATTERNS = [
    r'^\s*(hi|hello|hey|namaste|vanakkam|good\s+(morning|afternoon|evening)|who\s+are\s+you|what\s+can\s+you\s+do|help|start)\b',
    r'^\s*(thanks|thank\s+you|ok|okay|bye|goodbye)\b'
]

# Catalog / Meta intent keywords
CATALOG_PATTERNS = [
    r'\blist\s+(all\s+)?(the\s+)?([a-z\-]+\s+)*(documents?|speeches?|manuals?|circulars?|files?|years?|departments?|publications?)\b',
    r'\bwhat\s+([a-z\-]+\s+)*(documents?|speeches?|manuals?|circulars?|files?|years?|publications?)\s+(do\s+you\s+have|are\s+available|exist|are\s+there|in\s+the\s+database)\b',
    r'\bshow\s+(all\s+)?(the\s+)?([a-z\-]+\s+)*(documents?|speeches?|manuals?|circulars?|publications?)\b',
    r'\bavailable\s+([a-z\-]+\s+)*(documents?|speeches?|manuals?|circulars?|data|publications?)\b',
    r'\bwhich\s+([a-z\-]+\s+)*(years?|documents?|speeches?)\s+(are\s+available|do\s+you\s+have)\b'
]

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
    "reappropriation", "re-appropriation", "circular", "process", "eligibility",
    "objective", "objectives", "frbm", "compliance", "fiscal deficit"
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

# Year extraction regex
YEAR_RANGE_PATTERN = re.compile(r'\b(20\d{2}[-_]\d{2,4}|20\d{2})\b')

# Department hints
DEPARTMENT_HINTS = {
    "education": "School Education",
    "school": "School Education",
    "schools": "School Education",
    "agriculture": "Agriculture",
    "farmer": "Agriculture",
    "farmers": "Agriculture",
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

# Major Andhra Pradesh Government Schemes & their Parent Department
SCHEME_HINTS = {
    "amma vodi": {"official_name": "Jagananna Amma Vodi", "department": "School Education"},
    "ammavodi": {"official_name": "Jagananna Amma Vodi", "department": "School Education"},
    "rythu bharosa": {"official_name": "YSR Rythu Bharosa", "department": "Agriculture"},
    "annadata sukhibhava": {"official_name": "Annadata Sukhibhava", "department": "Agriculture"},
    "cheyutha": {"official_name": "YSR Cheyutha", "department": "Social Welfare"},
    "aasara": {"official_name": "YSR Aasara", "department": "Social Welfare"},
    "asara": {"official_name": "YSR Aasara", "department": "Social Welfare"},
    "vidya deevena": {"official_name": "Jagananna Vidya Deevena", "department": "Higher Education"},
    "vasathi deevena": {"official_name": "Jagananna Vasathi Deevena", "department": "Higher Education"},
    "aarogyasri": {"official_name": "Dr. YSR Aarogyasri", "department": "Health & Family Welfare"},
    "arogyasri": {"official_name": "Dr. YSR Aarogyasri", "department": "Health & Family Welfare"},
    "nadu nedu": {"official_name": "Mana Badi Nadu-Nedu", "department": "School Education"},
    "nethanna nestham": {"official_name": "YSR Nethanna Nestham", "department": "Industries & Commerce"},
    "matsyakara bharosa": {"official_name": "YSR Matsyakara Bharosa", "department": "Fisheries / Animal Husbandry"},
    "chedodu": {"official_name": "Jagananna Chedodu", "department": "Backward Classes Welfare"},
    "vahana mitra": {"official_name": "YSR Vahana Mitra", "department": "Transport & R&B"},
    "kapu nestham": {"official_name": "YSR Kapu Nestham", "department": "Backward Classes Welfare"},
    "ebc nestham": {"official_name": "YSR EBC Nestham", "department": "Social Welfare"},
    "sunna vaddi": {"official_name": "YSR Sunna Vaddi (Zero Interest)", "department": "Agriculture"},
    "polavaram": {"official_name": "Polavaram Irrigation Project", "department": "Water Resources"},
    "jalayagnam": {"official_name": "Jalayagnam Water Project", "department": "Water Resources"}
}

# Explicit State-level Total patterns
STATE_TOTAL_PATTERNS = [
    r'\bstate budget\b',
    r'\boverall budget\b',
    r'\btotal state budget\b',
    r'\btotal budget of ap\b',
    r'\btotal budget of andhra\b',
    r'\bstate expenditure\b',
    r'\btotal state outlay\b',
    r'\btotal budget of the state\b',
    r'\bstate-wide budget\b'
]

# Category hints
CATEGORY_HINTS = {
    "manual": "finance_manual",
    "rules": "finance_manual",
    "reappropriation": "finance_manual",
    "sanction": "finance_manual",
    "circular": "guidelines_circulars",
    "circulars": "guidelines_circulars",
    "guideline": "guidelines_circulars",
    "guidelines": "guidelines_circulars",
    "cbro": "guidelines_circulars",
    "metering": "guidelines_circulars",
    "memo": "guidelines_circulars",
    "speech": "budget_speech",
    "speeches": "budget_speech",
    "minister": "budget_speech",
    "survey": "socio_economic_survey",
    "socio": "socio_economic_survey",
    "frbm": "frbm_reports"
}


def normalize_raw_query(query: str) -> str:
    """
    Cleans raw user queries:
    1. Fixes concatenated words and numbers (e.g., '2024-15Budget' -> '2024-25 Budget').
    2. Corrects common year typos (e.g. '2024-15' -> '2024-25', '2026-17' -> '2026-27').
    3. Normalizes excessive whitespace and punctuation.
    """
    if not query:
        return ""
    
    q = query.strip()
    
    # Detach concatenated years and words: "2024-25Budget" -> "2024-25 Budget"
    q = re.sub(r'(\d{4}[-_]\d{2,4})([A-Za-z])', r'\1 \2', q)
    q = re.sub(r'([A-Za-z])(\d{4}[-_]\d{2,4})', r'\1 \2', q)
    
    # Correct inverted / typo financial years
    year_typos = {
        "2024-15": "2024-25",
        "2024_15": "2024-25",
        "2025-16": "2025-26",
        "2026-17": "2026-27",
        "2023-14": "2023-24",
        "2022-13": "2022-23",
        "2021-12": "2021-22"
    }
    for wrong, fixed in year_typos.items():
        q = q.replace(wrong, fixed)
        
    # Normalize spaces
    q = re.sub(r'\s+', ' ', q).strip()
    return q


def extract_financial_years(query: str) -> List[str]:
    """Extracts all financial years mentioned in the query."""
    normalized = normalize_raw_query(query)
    matches = YEAR_RANGE_PATTERN.findall(normalized)
    cleaned = []
    for m in matches:
        m_std = m.replace('_', '-')
        if m_std not in cleaned:
            cleaned.append(m_std)
    return cleaned


def extract_scheme(query: str) -> Optional[Dict[str, str]]:
    """Extracts known AP government welfare scheme from query if present."""
    q_lower = query.lower()
    for kw, scheme_info in SCHEME_HINTS.items():
        if re.search(rf'\b{re.escape(kw)}\b', q_lower):
            return {
                "keyword": kw,
                "scheme_name": scheme_info["official_name"],
                "department": scheme_info["department"]
            }
    return None


def is_state_total_query(query: str) -> bool:
    """Checks if query specifically asks for total state-wide budget/expenditure."""
    q_lower = query.lower()
    # If explicitly matching state total patterns
    if any(re.search(p, q_lower) for p in STATE_TOTAL_PATTERNS):
        return True
    # If query mentions "total budget" or "overall budget" but NO department and NO scheme
    scheme = extract_scheme(query)
    dept = None
    for kw in DEPARTMENT_HINTS:
        if re.search(rf'\b{kw}\b', q_lower):
            dept = kw
            break
    if not scheme and not dept:
        if re.search(r'\b(total budget|overall budget|state budget|annual budget)\b', q_lower):
            return True
    return False


def extract_department(query: str) -> Optional[str]:
    """Extracts likely department name from query or inferred from scheme."""
    q_lower = query.lower()
    for kw, dept_name in DEPARTMENT_HINTS.items():
        if re.search(rf'\b{kw}\b', q_lower):
            return dept_name
            
    # Infer parent department if a scheme is matched
    scheme_match = extract_scheme(query)
    if scheme_match:
        return scheme_match["department"]

    return None


def extract_category(query: str) -> Optional[str]:
    """Extracts category filter if specifically requested."""
    q_lower = query.lower()
    for kw, cat_name in CATEGORY_HINTS.items():
        if re.search(rf'\b{kw}\b', q_lower):
            return cat_name
    return None


def is_greeting(query: str) -> bool:
    """Checks if query is a greeting or general chitchat."""
    q_lower = query.lower().strip()
    return any(re.search(p, q_lower) for p in GREETING_PATTERNS)


def classify_query(query: str) -> QueryType:
    """
    Query classification:
    Returns: QueryType (GREETING | CATALOG | SQL | RAG | HYBRID | COMPARISON)
    """
    q_lower = query.lower().strip()

    # 1. Direct Greeting / conversational inquiry
    if is_greeting(query):
        return QueryType.GREETING

    # 2. Catalog / Meta intent
    if any(re.search(p, q_lower) for p in CATALOG_PATTERNS):
        return QueryType.CATALOG

    years = extract_financial_years(query)
    has_numerical = any(re.search(p, q_lower) for p in NUMERICAL_PATTERNS)
    has_comparison = any(kw in q_lower for kw in COMPARISON_KEYWORDS)
    has_explanatory = any(kw in q_lower for kw in EXPLANATORY_KEYWORDS)
    scheme_info = extract_scheme(query)

    # 3. Multi-year comparison
    if has_comparison or (len(years) > 1 and has_numerical):
        return QueryType.COMPARISON

    # 4. Scheme inquiry: Schemes have financial figures in speeches and policy guidelines
    # Always route to HYBRID so both vector narratives (speeches, gazettes) and SQL scheme tables are queried.
    if scheme_info:
        return QueryType.HYBRID

    # 5. Hybrid (asks for both numbers and qualitative explanation)
    if has_numerical and has_explanatory:
        return QueryType.HYBRID

    # 6. SQL (clean numerical question with department or explicit state total)
    if has_numerical and not has_explanatory:
        return QueryType.SQL

    # 7. Pure narrative / policy / guidelines / rules
    if has_explanatory and not has_numerical:
        return QueryType.RAG

    # 8. Default fallback to HYBRID
    return QueryType.HYBRID


def expand_query(query: str) -> List[str]:
    """
    Expands user query by injecting official AP government domain terminology.
    Translates colloquial queries into official terminology to boost BM25 + Vector recall.
    """
    expanded = [query]
    q_lower = query.lower()

    synonym_map = {
        "amma vodi": ["Jagananna Amma Vodi financial assistance to mothers", "School Education allocation", "direct benefit transfer DBT"],
        "ammavodi": ["Jagananna Amma Vodi financial assistance", "School Education allocation"],
        "rythu bharosa": ["YSR Rythu Bharosa input subsidy to farmers", "Agriculture budget allocation"],
        "annadata sukhibhava": ["Annadata Sukhibhava farmer financial support", "Agriculture allocation"],
        "cheyutha": ["YSR Cheyutha financial assistance to women", "Social Welfare"],
        "aasara": ["YSR Aasara SHG loan reimbursement", "Social Welfare DWCRA"],
        "vidya deevena": ["Jagananna Vidya Deevena fee reimbursement Higher Education"],
        "vasathi deevena": ["Jagananna Vasathi Deevena boarding hostel charges"],
        "aarogyasri": ["Dr. YSR Aarogyasri health care trust", "free medical treatment hospital"],
        "nadu nedu": ["Mana Badi Nadu-Nedu school infrastructure transformation"],
        "school": ["School Education Department", "Major Head 2202 General Education"],
        "education": ["School Education", "Higher Education Department"],
        "farmer": ["Agriculture & Allied Sectors", "Rythu Bharosa", "PM-KISAN input subsidy"],
        "agriculture": ["Agriculture Department", "Horticulture", "Price Stabilisation Fund"],
        "health": ["Health, Medical & Family Welfare", "Dr. YSR Aarogyasri healthcare"],
        "medical": ["Health, Medical & Family Welfare Department"],
        "hospital": ["Health & Family Welfare healthcare infrastructure"],
        "roads": ["Transport, Roads & Buildings Department"],
        "cbro": ["Comprehensive Budget Release Order (CBRO) guidelines quarterly regulation"],
        "manual": ["A.P. Budget Manual rules and procedures"],
        "reappropriation": ["re-appropriation of funds transfer of savings sanction powers AP Financial Code"],
        "re-appropriation": ["re-appropriation of budget funds transfer of savings AP Financial Code Article"],
        "sanction": ["powers of financial sanction Heads of Departments delegating authority"],
        "pension": ["Pay Revision Commission (PRC) pension and retirement benefits"],
        "welfare": ["Social Welfare", "Scheduled Castes SC component", "BC component"],
        "housing": ["Housing Department PM Awas Yojana"],
        "metering": ["Prepaid Smart Metering Government Departments billing"],
        "frbm": ["Fiscal Responsibility and Budget Management Act fiscal deficit targets revenue deficit"],
        "contingency": ["Andhra Pradesh Contingency Fund advances rules"],
        "speech": ["Budget Speech Finance Minister Annual Financial Statement", "key priorities and policy interventions"]
    }

    terms_added = []
    for trigger, official_terms in synonym_map.items():
        if trigger in q_lower:
            for term in official_terms:
                if term.lower() not in q_lower:
                    terms_added.append(term)

    if terms_added:
        augmented_query = f"{query} ({', '.join(terms_added[:3])})"
        expanded.append(augmented_query)

    return expanded


def route_query(query: str) -> Dict[str, Any]:
    """
    Primary routing function.
    Cleans raw query, normalizes typos, classifies intent, and extracts search entities.
    """
    normalized_q = normalize_raw_query(query)
    q_type = classify_query(normalized_q)

    # If greeting, return immediately with zero DB overhead
    if q_type == QueryType.GREETING:
        return {
            "original_query": query,
            "normalized_query": normalized_q,
            "expanded_queries": [normalized_q],
            "query_type": q_type,
            "primary_year": None,
            "all_years": [],
            "department": None,
            "scheme": None,
            "is_state_total": False,
            "category_filter": None,
            "requires_sql": False,
            "requires_vector": False
        }

    years = extract_financial_years(normalized_q)
    scheme_info = extract_scheme(normalized_q)
    department = extract_department(normalized_q)
    category = extract_category(normalized_q)
    expanded_queries = expand_query(normalized_q)
    is_state_total = is_state_total_query(normalized_q)

    decision = {
        "original_query": query,
        "normalized_query": normalized_q,
        "expanded_queries": expanded_queries,
        "query_type": q_type,
        "primary_year": years[0] if years else None,
        "all_years": years,
        "department": department,
        "scheme": scheme_info["scheme_name"] if scheme_info else None,
        "scheme_keyword": scheme_info["keyword"] if scheme_info else None,
        "is_state_total": is_state_total,
        "category_filter": category,
        "requires_sql": q_type in [QueryType.SQL, QueryType.HYBRID, QueryType.COMPARISON, QueryType.CATALOG],
        "requires_vector": q_type != QueryType.CATALOG
    }

    logger.info(
        f"Query routed -> Type: {q_type.value} | Years: {years} | Dept: {department} | Scheme: {decision['scheme']} | StateTotal: {is_state_total} | Cat: {category} | Normalized: '{normalized_q}'"
    )
    return decision
