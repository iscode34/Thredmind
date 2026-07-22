import os
import sys

# Ensure project root is in python module path for Vercel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routes import auth, chat, dashboard, documents, graph
from app.services.db_client import init_db



import logging

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception as e:
        logger.warning(f"Database initialization skipped or failed during startup: {e}")
    yield


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="Thredmind", version="0.1.0", lifespan=lifespan)

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception on {request.url.path}: {exc}", exc_info=True)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(
        content=f"<html><head><title>Application Error</title></head><body style='font-family:sans-serif;padding:2rem;'><h2>Application Error</h2><p>{str(exc)}</p></body></html>",
        status_code=500,
    )

app.include_router(auth.router, prefix="/auth", tags=["Auth"])

app.include_router(dashboard.router, tags=["Dashboard"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(chat.router, tags=["Chat"])
app.include_router(graph.router, tags=["Graph"])


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.png", include_in_schema=False)
async def favicon():
    return RedirectResponse(url="/static/img/favicon.png", status_code=302)


@app.get("/")

async def root(request: Request):
    """Landing page for visitors. Redirects to dashboard if already logged in."""
    from app.dependencies import get_current_user, theme_from_request
    from app.templating import templates

    user = get_current_user(request)
    if user:
        return RedirectResponse("/app")

    theme = theme_from_request(request)
    return templates.TemplateResponse("landing.html", {"request": request, "theme": theme})


@app.get("/home")
async def home(request: Request):
    """Landing page accessible to everyone — including logged-in users."""
    from app.dependencies import theme_from_request
    from app.templating import templates

    theme = theme_from_request(request)
    return templates.TemplateResponse("landing.html", {"request": request, "theme": theme})


@app.get("/study")
async def study_library(request: Request):
    from app.dependencies import get_current_user, theme_from_request
    from app.templating import templates
    from app.services.db_client import execute, execute_one
    from datetime import date

    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    theme = theme_from_request(request)

    # Get all documents
    rows = execute(
        """SELECT id, title, source_type, word_count, summary, category, is_favorite, created_at, parent_document_id
           FROM documents WHERE user_id = %s ORDER BY created_at DESC""",
        (user["id"],)
    ) or []

    documents = []
    parent_ids = set()
    for row in rows:
        d = dict(row)
        d["created_at"] = d["created_at"].strftime("%b %d, %Y") if d.get("created_at") else ""
        documents.append(d)
        if d.get("parent_document_id"):
            parent_ids.add(d["parent_document_id"])

    # Look up parent document titles for AI-generated docs
    parent_titles = {}
    if parent_ids:
        placeholders = ','.join(['%s'] * len(parent_ids))
        parent_rows = execute(
            f"SELECT id, title FROM documents WHERE id IN ({placeholders})",
            tuple(parent_ids)
        ) or []
        parent_titles = {p["id"]: p["title"] for p in parent_rows}

    # Attach parent title to each document
    for doc in documents:
        pid = doc.get("parent_document_id")
        doc["parent_title"] = parent_titles.get(pid, "") if pid else ""

    # Get study progress for all documents
    progress_rows = execute(
        """SELECT document_id, study_count, last_studied, next_review, review_interval, mastery, completed
           FROM study_progress WHERE user_id = %s""",
        (user["id"],)
    ) or []

    progress_map = {}
    due_docs = []
    today = date.today()
    for pr in progress_rows:
        p = dict(pr)
        p["last_studied"] = p["last_studied"].strftime("%b %d, %Y") if p.get("last_studied") else ""
        next_rev = p.get("next_review")
        if next_rev:
            if hasattr(next_rev, 'date'):
                next_rev_date = next_rev.date()
            else:
                next_rev_date = next_rev
            if next_rev_date <= today:
                due_docs.append(p["document_id"])
        progress_map[p["document_id"]] = p

    # Attach progress to each document
    studied_count = 0
    for doc in documents:
        prog = progress_map.get(doc["id"])
        doc["progress"] = prog
        if prog:
            studied_count += 1

    # Get user stats
    stats_row = execute_one(
        "SELECT current_streak, longest_streak, total_sessions FROM user_study_stats WHERE user_id = %s",
        (user["id"],)
    )

    stats = {
        "total_docs": len(documents),
        "studied": studied_count,
        "streak": stats_row["current_streak"] if stats_row else 0,
        "longest_streak": stats_row["longest_streak"] if stats_row else 0,
        "total_sessions": stats_row["total_sessions"] if stats_row else 0,
        "due_count": len(due_docs),
    }

    categories = execute(
        "SELECT name, color FROM categories WHERE user_id = %s ORDER BY name",
        (user["id"],)
    ) or []
    categories_list = [dict(c) for c in categories]

    return templates.TemplateResponse(
        "study_library.html",
        {"request": request, "user": user, "theme": theme,
         "documents": documents, "categories": categories_list,
         "stats": stats, "due_docs": due_docs,
         "sidebar_active": "study"}
    )
