from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies import get_current_user, theme_from_request

router = APIRouter()


@router.get("/app", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    from app.templating import templates
    from app.services.db_client import execute, execute_one
    from datetime import date
    theme = theme_from_request(request)
    
    # Document counts
    doc_count = execute_one(
        "SELECT COUNT(*) as count FROM documents WHERE user_id = %s",
        (user["id"],)
    )
    doc_count = doc_count["count"] if doc_count else 0
    
    # AI-generated document count
    ai_count = execute_one(
        "SELECT COUNT(*) as count FROM documents WHERE user_id = %s AND source_type = 'ai_generated'",
        (user["id"],)
    )
    ai_count = ai_count["count"] if ai_count else 0
    
    # Source type distribution
    source_rows = execute(
        """SELECT source_type, COUNT(*) as count FROM documents 
           WHERE user_id = %s AND source_type != 'ai_generated'
           GROUP BY source_type ORDER BY count DESC""",
        (user["id"],)
    ) or []
    source_dist = [{"type": r["source_type"], "count": r["count"]} for r in source_rows]
    
    # Recent documents
    recent_docs = execute(
        "SELECT id, title, source_type, summary, created_at FROM documents WHERE user_id = %s ORDER BY created_at DESC LIMIT 5",
        (user["id"],)
    ) or []
    recent_docs_list = []
    for doc in recent_docs:
        d = dict(doc)
        d["created_at"] = d["created_at"].strftime("%b %d, %Y") if d.get("created_at") else ""
        recent_docs_list.append(d)
    
    # Total word count
    words = execute_one(
        "SELECT COALESCE(SUM(word_count), 0) as total FROM documents WHERE user_id = %s",
        (user["id"],)
    )
    total_words = words["total"] if words else 0
    
    # Entity count
    entities_data = execute(
        "SELECT entities_json FROM documents WHERE user_id = %s AND entities_json IS NOT NULL AND entities_json::text != '{}'",
        (user["id"],)
    ) or []
    total_entities = 0
    for row in entities_data:
        entities = row["entities_json"]
        if isinstance(entities, dict):
            for key in entities:
                try:
                    val = entities[key]
                    if isinstance(val, list):
                        total_entities += len(val)
                except Exception:
                    pass
    
    # Study stats
    study_stats = execute_one(
        "SELECT current_streak, total_sessions FROM user_study_stats WHERE user_id = %s",
        (user["id"],)
    )
    streak = study_stats["current_streak"] if study_stats else 0
    total_sessions = study_stats["total_sessions"] if study_stats else 0
    
    # Documents studied
    studied_count = execute_one(
        "SELECT COUNT(*) as count FROM study_progress WHERE user_id = %s",
        (user["id"],)
    )
    studied_count = studied_count["count"] if studied_count else 0
    
    # Mastered documents count
    mastered_count = execute_one(
        "SELECT COUNT(*) as count FROM study_progress WHERE user_id = %s AND mastery = 'mastered'",
        (user["id"],)
    )
    mastered_count = mastered_count["count"] if mastered_count else 0
    
    # Documents due for review
    today = date.today()
    due_rows = execute(
        "SELECT d.id, d.title, sp.mastery, sp.next_review FROM study_progress sp JOIN documents d ON d.id = sp.document_id WHERE sp.user_id = %s ORDER BY sp.next_review ASC LIMIT 4",
        (user["id"],)
    ) or []
    due_docs = []
    for dr in due_rows:
        dd = dict(dr)
        nr = dd.get("next_review")
        if nr and hasattr(nr, 'date'):
            dd["is_due"] = nr.date() <= today
        else:
            dd["is_due"] = False
        due_docs.append(dd)
    
    # Category distribution
    cat_rows = execute(
        """SELECT c.name, c.color, COUNT(d.id) as count 
           FROM categories c 
           LEFT JOIN documents d ON d.category = c.name AND d.user_id = %s
           WHERE c.user_id = %s 
           GROUP BY c.name, c.color 
           ORDER BY count DESC LIMIT 5""",
        (user["id"], user["id"])
    ) or []
    categories = [{"name": r["name"], "color": r["color"], "count": r["count"]} for r in cat_rows]
    
    return templates.TemplateResponse(
        request=request,
        name="index.html", 
        context={
            "user": user, 
            "theme": theme, 
            "sidebar_active": "dashboard",
            "doc_count": doc_count,
            "ai_count": ai_count,
            "total_words": total_words,
            "total_entities": total_entities,
            "recent_docs": recent_docs_list,
            "streak": streak,
            "total_sessions": total_sessions,
            "studied_count": studied_count,
            "mastered_count": mastered_count,
            "due_docs": due_docs,
            "source_dist": source_dist,
            "categories": categories,
        }
    )

