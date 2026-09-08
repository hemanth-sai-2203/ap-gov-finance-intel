"""
LangGraph StateGraph Workflow for AP Government Finance Intelligence.

Implements an agentic state graph workflow:
1. Router Node (determines SQL vs RAG vs Hybrid)
2. SQL Retriever Node (executes deterministic database queries against Supabase PostgreSQL)
3. Hybrid RAG Retriever Node (Weaviate 768-dim Vector + BM25 + Cross-Encoder Reranking)
4. Unified Retrieval Node (combines multi-source evidence)
5. Synthesis Node (Evidence-grounded Gemini synthesis with inline citations)
"""
import logging
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END

from app.search.query_router import route_query, QueryType
from app.search.hybrid_search import hybrid_search
from app.search.sql_engine import (
    get_department_allocation,
    get_total_budget_by_year,
    get_top_departments_by_allocation
)
from app.search.engine import retrieve_evidence, EvidenceBundle
from app.core.llm_engine import generate_answer
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


# ─── 1. State Definition ───────────────────────────────────────────────────────

class FinanceGraphState(TypedDict):
    query: str
    query_type: str
    financial_year: Optional[str]
    category: Optional[str]
    department: Optional[str]
    top_k: int
    sql_results: Optional[List[Dict[str, Any]]]
    rag_results: Optional[List[Dict[str, Any]]]
    answer: Optional[str]
    citations: Optional[List[Dict[str, Any]]]
    has_sql_evidence: bool
    has_rag_evidence: bool


# ─── 2. Graph Nodes ────────────────────────────────────────────────────────────

def router_node(state: FinanceGraphState) -> FinanceGraphState:
    """Classifies the query intent and extracts financial year, department, and category."""
    decision = route_query(state["query"])
    return {
        **state,
        "query_type": decision.get("query_type", QueryType.RAG),
        "financial_year": state.get("financial_year") or decision.get("primary_year") or decision.get("financial_year"),
        "department": state.get("department") or decision.get("department"),
        "category": state.get("category") or decision.get("category_filter"),
    }


def sql_retriever_node(state: FinanceGraphState) -> FinanceGraphState:
    """Executes deterministic SQL queries against Supabase PostgreSQL tables."""
    db = SessionLocal()
    sql_data = []
    try:
        dept = state.get("department")
        fy = state.get("financial_year")

        if dept:
            sql_data = get_department_allocation(dept, financial_year=fy, db=db)
        elif fy:
            total = get_total_budget_by_year(fy, db=db)
            if total and total.get("total_budget_estimate_cr"):
                sql_data = [total]

        if not sql_data and fy:
            sql_data = get_top_departments_by_allocation(fy, limit=5, db=db)
    finally:
        db.close()

    return {
        **state,
        "sql_results": sql_data,
        "has_sql_evidence": bool(sql_data)
    }


def rag_retriever_node(state: FinanceGraphState) -> FinanceGraphState:
    """Executes Weaviate Dense Vector + BM25 hybrid search + Cross-Encoder reranking."""
    rag_data = []
    try:
        rag_data = hybrid_search(
            query=state["query"],
            top_k=state.get("top_k", 5),
            financial_year=state.get("financial_year"),
            category=state.get("category"),
            use_reranker=True
        )
    except Exception as e:
        logger.warning(f"RAG retrieval node error: {e}")

    return {
        **state,
        "rag_results": rag_data,
        "has_rag_evidence": bool(rag_data)
    }


def hybrid_retriever_node(state: FinanceGraphState) -> FinanceGraphState:
    """Executes both SQL lookups and RAG document retrieval for complex queries."""
    s1 = sql_retriever_node(state)
    s2 = rag_retriever_node(state)
    return {
        **state,
        "sql_results": s1.get("sql_results"),
        "rag_results": s2.get("rag_results"),
        "has_sql_evidence": s1.get("has_sql_evidence", False),
        "has_rag_evidence": s2.get("has_rag_evidence", False)
    }


def synthesis_node(state: FinanceGraphState) -> FinanceGraphState:
    """Synthesizes final answer using EvidenceBundle and Google Gemini 2.5 Flash."""
    evidence = retrieve_evidence(
        query=state["query"],
        top_k=state.get("top_k", 5),
        force_year=state.get("financial_year"),
        force_category=state.get("category")
    )

    synthesis_result = generate_answer(
        query=state["query"],
        evidence=evidence
    )

    return {
        **state,
        "answer": synthesis_result["answer"],
        "citations": synthesis_result["citations"],
        "has_sql_evidence": bool(evidence.sql_records or evidence.sql_aggregations),
        "has_rag_evidence": bool(evidence.passages)
    }


# ─── 3. Conditional Routing Function ──────────────────────────────────────────

def decide_next_node(state: FinanceGraphState) -> str:
    q_type = state.get("query_type")
    if q_type == QueryType.SQL:
        return "sql_retriever"
    elif q_type == QueryType.RAG:
        return "rag_retriever"
    else:
        return "hybrid_retriever"


# ─── 4. Build LangGraph Workflow ───────────────────────────────────────────────

def build_finance_graph():
    workflow = StateGraph(FinanceGraphState)

    # Add Nodes
    workflow.add_node("router", router_node)
    workflow.add_node("sql_retriever", sql_retriever_node)
    workflow.add_node("rag_retriever", rag_retriever_node)
    workflow.add_node("hybrid_retriever", hybrid_retriever_node)
    workflow.add_node("synthesizer", synthesis_node)

    # Set Entry Point
    workflow.set_entry_point("router")

    # Add Conditional Routing Edge
    workflow.add_conditional_edges(
        "router",
        decide_next_node,
        {
            "sql_retriever": "sql_retriever",
            "rag_retriever": "rag_retriever",
            "hybrid_retriever": "hybrid_retriever"
        }
    )

    # Connect retrieval nodes to synthesis
    workflow.add_edge("sql_retriever", "synthesizer")
    workflow.add_edge("rag_retriever", "synthesizer")
    workflow.add_edge("hybrid_retriever", "synthesizer")

    # Finish
    workflow.add_edge("synthesizer", END)

    return workflow.compile()


# Global compiled graph instance
finance_graph = build_finance_graph()


def run_langgraph_query(
    query: str,
    financial_year: Optional[str] = None,
    department: Optional[str] = None,
    category: Optional[str] = None,
    top_k: int = 5
) -> Dict[str, Any]:
    """Runs the full query through the compiled LangGraph state machine."""
    initial_state: FinanceGraphState = {
        "query": query,
        "query_type": "",
        "financial_year": financial_year,
        "department": department,
        "category": category,
        "top_k": top_k,
        "sql_results": None,
        "rag_results": None,
        "answer": None,
        "citations": None,
        "has_sql_evidence": False,
        "has_rag_evidence": False
    }

    result_state = finance_graph.invoke(initial_state)
    return result_state
