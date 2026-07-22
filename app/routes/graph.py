"""Graph route: knowledge graph visualization and API."""
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.dependencies import get_current_user, theme_from_request

router = APIRouter()


@router.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    from app.templating import templates
    theme = theme_from_request(request)

    from app.services.db_client import execute
    categories = execute(
        "SELECT name, color FROM categories WHERE user_id = %s ORDER BY name",
        (user["id"],)
    ) or []
    categories_list = [dict(c) for c in categories]

    from app.services.knowledge_graph import get_graph_stats
    stats = get_graph_stats(user["id"])

    return templates.TemplateResponse(
        request=request,
        name="graph.html",
        context={
            "user": user, "theme": theme,
            "sidebar_active": "graph", "categories": categories_list, "stats": stats
        }
    )



@router.get("/graph/data")
async def graph_data(
    request: Request,
    category: str = Query(""),
    keyword: str = Query(""),
    entity_type: str = Query(""),
):
    """Serve knowledge graph JSON for Cytoscape.js."""
    user = get_current_user(request)
    if not user:
        return {"nodes": [], "edges": []}

    from app.services.knowledge_graph import get_user_graph
    try:
        return get_user_graph(
            user["id"],
            filter_category=category or None,
            filter_keyword=keyword or None,
            filter_entity_type=entity_type or None,
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f"graph_data error: {exc}", exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/graph/stats")
async def graph_stats(request: Request):
    user = get_current_user(request)
    if not user:
        return {}
    from app.services.knowledge_graph import get_graph_stats
    return get_graph_stats(user["id"])


@router.post("/graph/rebuild")
async def rebuild_graph(request: Request):
    """Hard-reset and rebuild the entire knowledge graph for the current user."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    try:
        from app.services.knowledge_graph import rebuild_graph_for_user
        rebuild_graph_for_user(user["id"])
        return JSONResponse({"ok": True, "message": "Graph rebuilt successfully."})
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f"rebuild_graph error: {exc}", exc_info=True)
        return JSONResponse({"error": str(exc)}, status_code=500)
