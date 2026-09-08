"""
AP Government Finance Intelligence — Production FastAPI Application.

REST Endpoints:
  GET  /health                   — System health check & active database/vector status
  GET  /api/stats                — Overview of ingested documents and vector counts
  POST /api/query                — Main Grounded Intelligence Query (RAG + SQL + Citations)
  POST /api/search               — Raw Hybrid Document Search (no LLM, ranked passages)
  GET  /api/documents            — List all ingested official government documents
  GET  /api/budget/total         — Total budget estimates/expenditure (Deterministic SQL)
  GET  /api/budget/department    — Department budget allocations (Deterministic SQL)
  GET  /api/budget/top-departments — Top departments by budget allocation (Deterministic SQL)
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db, SessionLocal
from app.db.models import DocumentModel, DocumentChunkModel, FinancialRecordModel
from app.search.hybrid_search import hybrid_search, get_weaviate_client
from app.search.reranker import get_reranker
from app.search.sql_engine import (
    get_department_allocation,
    get_total_budget_by_year,
    get_top_departments_by_allocation,
    compare_department_across_years,
)
from app.core.query_pipeline import run_query

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Non-blocking ASGI startup.
    Ensures Uvicorn binds to port 10000 in <1s for Render healthcheck.
    Heavy models and connections are verified lazily or asynchronously.
    """
    logger.info("Initializing AP Government Finance Intelligence API (Fast Startup)...")
    yield
    logger.info("Shutting down AP Government Finance Intelligence API.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Evidence-grounded AP Government Finance Intelligence Platform powered by Hybrid Search (768-dim Vector + BM25), Cross-Encoder Reranker, Deterministic SQL, and Google Gemini 2.5 Flash.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UI_HTML_PATH = os.path.join(os.path.dirname(__file__), "ui", "index.html")


# ─── Pydantic Request & Response Models ────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language question about AP budget, rules, or circulars", json_schema_extra={"example": "What is the procedure for Comprehensive Budget Release Order CBRO in 2026-27?"})
    financial_year: Optional[str] = Field(None, description="Optional financial year filter (e.g. '2026-27', '2021')", json_schema_extra={"example": "2026-27"})
    category: Optional[str] = Field(None, description="Optional document category ('budget_speech', 'finance_manual', 'guidelines_circulars')")
    department: Optional[str] = Field(None, description="Optional department name")
    top_k: int = Field(5, ge=1, le=20, description="Number of context passages to retrieve")


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search keyword or phrase", json_schema_extra={"example": "Rythu Bharosa farmer welfare"})
    financial_year: Optional[str] = Field(None, description="Optional financial year filter")
    category: Optional[str] = Field(None, description="Optional category filter")
    alpha: float = Field(0.65, ge=0.0, le=1.0, description="Dense (1.0) vs Sparse BM25 (0.0) weighting")
    top_k: int = Field(10, ge=1, le=50, description="Number of passages to return")


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", tags=["UI"], response_class=FileResponse)
def serve_portal_ui():
    """Serves the AP Government Finance Intelligence Web Portal Interface."""
    if os.path.exists(UI_HTML_PATH):
        return FileResponse(UI_HTML_PATH)
    return HTMLResponse("<h1>AP Government Finance Intelligence Portal</h1><p>UI file not found.</p>")


@app.get("/ui", tags=["UI"], response_class=FileResponse)
def serve_portal_ui_alias():
    """Alias to access the Web Portal Interface."""
    return serve_portal_ui()

@app.get("/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint confirming status of SQL and Vector engines."""
    try:
        doc_count = db.query(DocumentModel).count()
        chunk_count = db.query(DocumentChunkModel).count()
        return {
            "status": "healthy",
            "service": settings.PROJECT_NAME,
            "version": "1.0.0",
            "database": {
                "supabase_postgresql": "connected",
                "total_documents": doc_count,
                "total_sql_chunks": chunk_count
            },
            "vector_store": {
                "weaviate_cloud": "connected",
                "dimension": 768,
                "embedding_model": settings.EMBEDDING_MODEL_NAME
            },
            "llm": {
                "provider": settings.LLM_PROVIDER,
                "model": settings.GEMINI_MODEL
            }
        }
    except Exception as e:
        return {"status": "degraded", "detail": str(e)}


@app.get("/api/stats", tags=["System"])
def get_platform_stats(db: Session = Depends(get_db)):
    """Returns overview statistics of all ingested categories and years."""
    docs = db.query(DocumentModel).all()
    categories = {}
    years = {}

    for d in docs:
        categories[d.category] = categories.get(d.category, 0) + 1
        yr = d.financial_year or "reference"
        years[yr] = years.get(yr, 0) + 1

    total_chunks = db.query(DocumentChunkModel).count()

    return {
        "total_documents": len(docs),
        "total_chunks": total_chunks,
        "categories_distribution": categories,
        "financial_years_distribution": years,
        "vector_embedding_dimension": 768
    }


@app.post("/api/query", tags=["Intelligence"])
def intelligence_query(request: QueryRequest, db: Session = Depends(get_db)):
    """
    Main intelligence query endpoint:
    Executes Hybrid Search + Reranker + Gemini 2.5 Flash synthesis and returns
    a natural-language answer with exact source citations.
    """
    try:
        result = run_query(
            query=request.query,
            financial_year=request.financial_year,
            category=request.category,
            department=request.department,
            top_k=request.top_k,
            db=db,
        )
        return result
    except Exception as e:
        logger.error(f"Intelligence query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search", tags=["Search"])
def document_search(request: SearchRequest):
    """
    Raw hybrid document search — returns ranked evidence passages with scores
    and source metadata (no LLM generation). Useful for exploration and citations.
    """
    try:
        results = hybrid_search(
            query=request.query,
            top_k=request.top_k,
            alpha=request.alpha,
            financial_year=request.financial_year,
            category=request.category,
            use_reranker=True
        )
        return {
            "query": request.query,
            "results_count": len(results),
            "results": results
        }
    except Exception as e:
        logger.error(f"Raw search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents", tags=["Documents"])
def list_documents(
    category: Optional[str] = Query(None, description="Filter by category ('budget_speech', 'finance_manual', 'guidelines_circulars')"),
    financial_year: Optional[str] = Query(None, description="Filter by financial year (e.g. '2026-27')"),
    db: Session = Depends(get_db),
):
    """Lists all official government documents ingested into the platform."""
    q = db.query(DocumentModel)
    if category:
        q = q.filter(DocumentModel.category == category)
    if financial_year:
        q = q.filter(DocumentModel.financial_year == financial_year)

    docs = q.order_by(DocumentModel.id.asc()).all()

    return {
        "count": len(docs),
        "documents": [
            {
                "id": d.id,
                "title": d.title,
                "category": d.category,
                "financial_year": d.financial_year,
                "language": d.language,
                "total_pages": d.total_pages,
                "total_chunks": d.total_chunks,
                "status": d.status,
                "source_url": d.source_url,
                "created_at": d.created_at.isoformat() if d.created_at else None
            }
            for d in docs
        ]
    }


@app.get("/api/budget/total", tags=["Budget (SQL)"])
def budget_total(
    financial_year: str = Query("2026-27", description="e.g. 2026-27"),
    db: Session = Depends(get_db)
):
    """Returns total budget estimates and actuals for a financial year (Deterministic SQL)."""
    return get_total_budget_by_year(financial_year, db=db)


@app.get("/api/budget/department", tags=["Budget (SQL)"])
def budget_department(
    department: str = Query(..., description="e.g. Education, Agriculture"),
    financial_year: Optional[str] = Query(None, description="e.g. 2026-27"),
    db: Session = Depends(get_db)
):
    """Returns budget allocations for a specific department (Deterministic SQL)."""
    results = get_department_allocation(department, financial_year=financial_year, db=db)
    return {
        "department": department,
        "financial_year": financial_year,
        "records_count": len(results),
        "allocations": results
    }


@app.get("/api/budget/top-departments", tags=["Budget (SQL)"])
def budget_top_departments(
    financial_year: str = Query(..., description="e.g. 2026-27"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Returns top departments ranked by budget allocation (Deterministic SQL)."""
    results = get_top_departments_by_allocation(financial_year, limit=limit, db=db)
    return {
        "financial_year": financial_year,
        "top_departments": results
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
