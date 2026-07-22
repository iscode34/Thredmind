import json
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Form, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies import get_current_user, theme_from_request
from app.services.db_client import execute, execute_one
from app.services.document_parser import extract_text_from_file
from app.services.web_scraper import fetch_and_extract
from app.services.ai_processor import process_content
from app.services.embedding_service import generate_embedding, store_embedding
from app.config import settings

router = APIRouter()


@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    from app.templating import templates
    theme = theme_from_request(request)
    return templates.TemplateResponse("upload.html", {"request": request, "user": user, "theme": theme, "sidebar_active": "upload"})


@router.post("/upload", response_class=HTMLResponse)
async def upload_document(request: Request, file: UploadFile = File(...)):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)

    try:
        file_bytes = await file.read()
        text, source_type = extract_text_from_file(file_bytes, file.filename)
    except ValueError as e:
        return HTMLResponse(f"""<div id="upload-error" class="text-error text-sm">{str(e)}</div>""", status_code=400)
    except Exception:
        return HTMLResponse("""<div id="upload-error" class="text-error text-sm">Failed to read file</div>""", status_code=400)

    if not text.strip():
        return HTMLResponse("""<div id="upload-error" class="text-error text-sm">No readable text found in file</div>""", status_code=400)

    word_count = len(text.split())

    doc_id = str(uuid.uuid4())
    title = file.filename.rsplit(".", 1)[0] if "." in file.filename else file.filename

    execute(
        """INSERT INTO documents (id, user_id, title, source_type, content_text, word_count)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (doc_id, user["id"], title, source_type, text, word_count),
    )

    return _process_and_respond(doc_id, user["id"])


@router.post("/import-url", response_class=HTMLResponse)
async def import_url(request: Request, url: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return HTMLResponse("""<div id="upload-error" class="text-error text-sm">Invalid URL. Must start with http:// or https://</div>""", status_code=400)

    try:
        text, page_title = fetch_and_extract(url)
    except ValueError as e:
        return HTMLResponse(f"""<div id="upload-error" class="text-error text-sm">{str(e)}</div>""", status_code=400)
    except Exception:
        return HTMLResponse("""<div id="upload-error" class="text-error text-sm">Failed to fetch page content</div>""", status_code=400)

    word_count = len(text.split())
    title = page_title or url.rsplit("/", 1)[-1] or "Web Page"

    doc_id = str(uuid.uuid4())
    execute(
        """INSERT INTO documents (id, user_id, title, source_type, source_url, content_text, word_count)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (doc_id, user["id"], title, "url", url, text, word_count),
    )

    return _process_and_respond(doc_id, user["id"])


@router.get("", response_class=HTMLResponse)
async def list_documents(request: Request, tab: str = "all", category: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    from app.templating import templates
    theme = theme_from_request(request)
    
    # Build query based on tab filter
    base_query = """SELECT id, title, source_type, source_url, summary, entities_json, keywords,
                  word_count, created_at, category, is_favorite
           FROM documents WHERE user_id = %s"""
    params = [user["id"]]
    
    if tab == "documents":
        base_query += " AND source_type != 'url' AND source_type != 'ai_generated'"
    elif tab == "urls":
        base_query += " AND source_type = 'url'"
    elif tab == "favorites":
        base_query += " AND is_favorite = true"
    elif tab == "ai":
        base_query += " AND source_type = 'ai_generated'"
    
    if category:
        base_query += " AND category = %s"
        params.append(category)
    
    base_query += " ORDER BY created_at DESC"
    
    rows = execute(base_query, tuple(params))
    documents = []
    for row in rows:
        doc = dict(row)
        doc["created_at"] = doc["created_at"].strftime("%b %d, %Y")
        if doc.get("entities_json"):
            doc["entities_json"] = doc["entities_json"] if isinstance(doc["entities_json"], dict) else json.loads(str(doc["entities_json"]))
        if doc.get("keywords"):
            doc["keywords"] = doc["keywords"] if isinstance(doc["keywords"], list) else []
        documents.append(doc)
    
    # Get all categories for filter dropdown
    categories = execute(
        "SELECT name, color FROM categories WHERE user_id = %s ORDER BY name",
        (user["id"],)
    )
    categories_list = [dict(cat) for cat in categories]

    return templates.TemplateResponse(
        "documents.html",
        {
            "request": request, 
            "user": user, 
            "theme": theme, 
            "documents": documents, 
            "categories": categories_list,
            "current_tab": tab,
            "current_category": category,
            "sidebar_active": "documents"
        },
    )


@router.get("/categories", response_class=HTMLResponse)
async def list_categories(request: Request):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)
    
    rows = execute(
        "SELECT id, name, color FROM categories WHERE user_id = %s ORDER BY name",
        (user["id"],)
    ) or []
    categories = [dict(row) for row in rows]
    
    return HTMLResponse(
        content=json.dumps(categories),
        media_type="application/json"
    )


@router.post("/categories")
async def create_category(request: Request, name: str = Form(...), color: str = Form("#60a5fa")):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)
    
    try:
        execute(
            "INSERT INTO categories (user_id, name, color) VALUES (%s, %s, %s)",
            (user["id"], name, color)
        )
        response = HTMLResponse(content="")
        response.headers["HX-Refresh"] = "true"
        return response
    except Exception as e:
        return HTMLResponse(f"Error creating category: {str(e)}", status_code=400)


@router.delete("/categories/{cat_id}")
async def delete_category(request: Request, cat_id: str):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)
    
    # Get category name before deleting (so we can clear it from documents)
    cat_row = execute_one(
        "SELECT name FROM categories WHERE id = %s AND user_id = %s",
        (cat_id, user["id"])
    )
    if cat_row:
        execute(
            "UPDATE documents SET category = NULL WHERE category = %s AND user_id = %s",
            (cat_row["name"], user["id"])
        )
        execute(
            "DELETE FROM categories WHERE id = %s AND user_id = %s",
            (cat_id, user["id"])
        )
    
    response = HTMLResponse(content="")
    response.headers["HX-Refresh"] = "true"
    return response


@router.get("/study-next", response_class=HTMLResponse)
async def study_next_document(request: Request):
    """Return the URL of the next unstudied document, or the first document."""
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)

    row = execute_one(
        """SELECT d.id FROM documents d
           LEFT JOIN study_progress sp ON d.id = sp.document_id AND sp.user_id = %s
           WHERE d.user_id = %s AND sp.id IS NULL
           ORDER BY d.created_at ASC LIMIT 1""",
        (user["id"], user["id"])
    )

    if not row:
        row = execute_one(
            """SELECT d.id FROM documents d
               JOIN study_progress sp ON d.id = sp.document_id AND sp.user_id = %s
               WHERE d.user_id = %s
               ORDER BY sp.next_review ASC NULLS LAST LIMIT 1""",
            (user["id"], user["id"])
        )

    if row:
        return HTMLResponse(content=f"/api/documents/{row['id']}/study-page")
    return HTMLResponse(content="/study")


@router.get("/{doc_id}", response_class=HTMLResponse)
async def view_document(request: Request, doc_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    from app.templating import templates
    theme = theme_from_request(request)
    row = execute_one(
        """SELECT id, title, source_type, source_url, content_text, summary, entities_json,
                  keywords, word_count, created_at
           FROM documents WHERE id = %s AND user_id = %s""",
        (doc_id, user["id"]),
    )
    if not row:
        return HTMLResponse("Document not found", status_code=404)

    doc = dict(row)
    doc["created_at"] = doc["created_at"].strftime("%b %d, %Y at %H:%M")
    if doc.get("entities_json"):
        doc["entities_json"] = doc["entities_json"] if isinstance(doc["entities_json"], dict) else json.loads(str(doc["entities_json"]))
    if doc.get("keywords"):
        doc["keywords"] = doc["keywords"] if isinstance(doc["keywords"], list) else []

    reading_time = max(1, (doc["word_count"] or 0) // 200)

    # Get all categories for selector
    categories = execute(
        "SELECT name, color FROM categories WHERE user_id = %s ORDER BY name",
        (user["id"],)
    )
    categories_list = [dict(cat) for cat in categories]

    return templates.TemplateResponse(
        "document_detail.html",
        {"request": request, "user": user, "theme": theme, "doc": doc, "reading_time": reading_time, "categories": categories_list, "sidebar_active": "documents"},
    )


@router.post("/{doc_id}/delete")
async def delete_document(doc_id: str):
    execute("DELETE FROM documents WHERE id = %s", (doc_id,))
    response = HTMLResponse(content="")
    response.headers["HX-Redirect"] = "/api/documents"
    return response


def _process_and_respond(doc_id: str, user_id: str):
    import time
    start_time = time.time()

    doc = execute_one(
        "SELECT id, title, source_type, source_url, content_text, word_count, created_at FROM documents WHERE id = %s",
        (doc_id,),
    )
    if not doc:
        return HTMLResponse("Document not found", status_code=404)

    doc = dict(doc)
    text = doc.get("content_text", "")
    ai_used = ""

    try:
        result = process_content(text)
        keywords = result.get("keywords", [])
        execute(
            """UPDATE documents SET summary = %s, entities_json = %s, keywords = %s, updated_at = now()
               WHERE id = %s""",
            (result.get("summary", ""), json.dumps(result.get("entities", {})), keywords, doc_id),
        )
        doc["summary"] = result.get("summary", "")
        doc["entities_json"] = result.get("entities", {})
        doc["keywords"] = keywords
        ai_used = "DeepSeek" if settings.DEEPSEEK_API_KEY else "AI"
    except Exception:
        doc["summary"] = "AI processing skipped (API unavailable)"
        doc["entities_json"] = {}
        doc["keywords"] = []
        ai_used = "skipped"

    try:
        embedding = generate_embedding(doc.get("summary", text[:500]))
        store_embedding(doc_id, embedding)
    except Exception:
        pass

    # Populate knowledge graph: extract entities, create cross-document links
    try:
        from app.services.knowledge_graph import process_document_for_graph
        process_document_for_graph(doc_id, user_id)
    except Exception:
        pass

    elapsed = round(time.time() - start_time, 1)
    doc["created_at"] = doc["created_at"].strftime("%B %d, %Y")
    reading_time = max(1, (doc.get("word_count", 0)) // 200)
    word_count = doc.get("word_count", 0)
    summary = doc.get("summary", "")
    entities = doc.get("entities_json", {})
    kw_list = doc.get("keywords", [])
    title = doc.get("title", "Untitled")

    source_icon = {"pdf": "text-red-400", "docx": "text-blue-400", "pptx": "text-orange-400", "txt": "text-emerald-400", "md": "text-emerald-400", "url": "text-sky-400"}.get(doc.get("source_type", ""), "text-fg-dim")

    people = entities.get("people", [])
    topics = entities.get("topics", [])
    orgs = entities.get("organizations", [])
    dates_list = entities.get("dates", [])

    topic_tags = "".join(f'<span class="px-2.5 py-1 rounded-lg bg-accent-bg text-xs text-fg-muted font-medium">{t}</span>' for t in topics[:6])
    people_tags = "".join(f'<span class="px-2.5 py-1 rounded-lg bg-blue-500/10 text-xs text-blue-400 font-medium">{p}</span>' for p in people[:4])
    keyword_tags = "".join(f'<span class="px-2.5 py-1 rounded-lg bg-accent-bg text-xs text-fg-muted font-medium">{kw}</span>' for kw in kw_list[:8])

    entity_section = ""
    if people or orgs or dates_list:
        entity_rows = []
        if people:
            entity_rows.append(f"""<div><span class="text-xs font-semibold text-fg-dim uppercase tracking-wider">People</span><div class="flex flex-wrap gap-1.5 mt-1.5">{people_tags}</div></div>""")
        if orgs:
            org_tags = "".join(f'<span class="px-2.5 py-1 rounded-lg bg-violet-500/10 text-xs text-violet-400 font-medium">{o}</span>' for o in orgs[:4])
            entity_rows.append(f"""<div><span class="text-xs font-semibold text-fg-dim uppercase tracking-wider">Organizations</span><div class="flex flex-wrap gap-1.5 mt-1.5">{org_tags}</div></div>""")
        if dates_list:
            date_tags = "".join(f'<span class="px-2.5 py-1 rounded-lg bg-amber-500/10 text-xs text-amber-400 font-medium">{d}</span>' for d in dates_list[:4])
            entity_rows.append(f"""<div><span class="text-xs font-semibold text-fg-dim uppercase tracking-wider">Timeline</span><div class="flex flex-wrap gap-1.5 mt-1.5">{date_tags}</div></div>""")
        entity_section = f"""<div class="bg-bg-input border border-border rounded-xl p-4 space-y-3">{"".join(entity_rows)}</div>"""

    return HTMLResponse(f"""
    <script>setTimeout(() => document.getElementById('processing-result')?.scrollIntoView({{behavior:'smooth',block:'start'}}), 100)</script>

    <div id="processing-result" class="space-y-5" style="scroll-margin-top:80px">
        <div class="flex items-center gap-3 p-4 bg-emerald-500/5 border border-emerald-500/10 rounded-2xl">
            <div class="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center flex-shrink-0">
                <svg class="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 13l4 4L19 7"/></svg>
            </div>
            <div class="flex-1 min-w-0">
                <p class="font-semibold text-fg text-sm">Processing complete</p>
                <p class="text-xs text-fg-dim">{title} &middot; {word_count} words &middot; {reading_time} min read &middot; {elapsed}s via {ai_used}</p>
            </div>
            <a href="/api/documents/{doc_id}" class="flex-shrink-0 px-3 py-1.5 rounded-lg bg-accent-bg text-xs text-fg-muted font-medium hover:bg-accent-bg/70 transition-colors">View Details</a>
        </div>

        <div class="bg-bg-card border border-border rounded-2xl overflow-hidden">
            <div class="px-5 py-3 border-b border-border flex items-center gap-2">
                <svg class="w-4 h-4 text-fg-dim" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 6h16M4 10h16M4 14h16M4 18h16"/></svg>
                <h4 class="text-xs font-semibold text-fg-dim uppercase tracking-wider">AI Summary</h4>
            </div>
            <div class="p-5">
                <p class="text-sm text-fg-muted leading-relaxed">{summary or 'Summary generation unavailable. Try again later.'}</p>
            </div>
        </div>

        {"<div class=\"bg-bg-card border border-border rounded-2xl overflow-hidden\"><div class=\"px-5 py-3 border-b border-border\"><h4 class=\"text-xs font-semibold text-fg-dim uppercase tracking-wider\">Key Topics</h4></div><div class=\"p-5 flex flex-wrap gap-2\">" + topic_tags + "</div></div>" if topic_tags else ""}

        {entity_section}

        {"<div class=\"bg-bg-card border border-border rounded-2xl overflow-hidden\"><div class=\"px-5 py-3 border-b border-border\"><h4 class=\"text-xs font-semibold text-fg-dim uppercase tracking-wider\">Keywords</h4></div><div class=\"p-5 flex flex-wrap gap-2\">" + keyword_tags + "</div></div>" if keyword_tags else ""}

        <div class="flex flex-wrap gap-2">
            <a href="/api/documents/{doc_id}" class="px-4 py-2.5 rounded-xl bg-accent text-accent-text text-sm font-medium hover:opacity-90 transition-opacity flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                View Full Document
            </a>
            <a href="/api/documents/{doc_id}#quiz" class="px-4 py-2.5 rounded-xl bg-accent-bg text-fg text-sm font-medium hover:bg-accent-bg/70 transition-colors flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                Generate Quiz
            </a>
            <a href="/api/documents/upload" class="px-4 py-2.5 rounded-xl bg-accent-bg text-fg-muted text-sm font-medium hover:text-fg transition-colors">
                Add Another
            </a>
        </div>
    </div>
    """)



@router.post("/{doc_id}/quiz", response_class=HTMLResponse)
async def generate_quiz(doc_id: str):
    row = execute_one(
        "SELECT id, title, content_text, summary FROM documents WHERE id = %s",
        (doc_id,),
    )
    if not row:
        return HTMLResponse("""<div class="text-error text-sm">Document not found</div>""", status_code=404)

    doc = dict(row)
    text = doc.get("content_text", "")[:8000]

    quiz_prompt = f"""Based on the following document content, generate 5 quiz questions in JSON format.
Return ONLY a JSON array of objects, each with: "question" (string), "options" (array of 4 strings), "answer" (index 0-3), "explanation" (string).

Document content:
{text}

Output format:
[{{"question": "...", "options": ["A", "B", "C", "D"], "answer": 0, "explanation": "..."}}]"""

    from app.services.ai_client import chat_completion as _ai_chat
    try:
        result = _ai_chat(
            messages=[{"role": "user", "content": quiz_prompt}],
            temperature=0.7,
            max_tokens=2000,
        )
        content = result["content"]
        if content.startswith("```"):
            content = "\n".join(content.split("\n")[1:-1])
        questions = json.loads(content)
    except Exception:
        questions = [
            {"question": "Quiz generation unavailable. Try again later.", "options": ["-", "-", "-", "-"], "answer": 0, "explanation": "The AI service could not generate questions at this time."}
        ]

    quiz_html = ""
    for i, q in enumerate(questions):
        opts_html = "".join(
            f'<div class="quiz-option flex items-center gap-3 p-3 rounded-xl border border-border hover:border-fg-muted/30 cursor-pointer transition-colors" data-correct="{str(j == q.get("answer", 0)).lower()}" onclick="selectQuiz(this,{i})"><span class="w-5 h-5 rounded-full border-2 border-border flex-shrink-0 flex items-center justify-center"><span class="w-2 h-2 rounded-full bg-emerald-400 hidden quiz-dot"></span></span><span class="text-sm text-fg-muted">{o}</span></div>'
            for j, o in enumerate(q.get("options", []))
        )
        answer_idx = q.get("answer", 0)
        correct_option = q.get("options", ["", "", "", ""])[answer_idx] if isinstance(q.get("options"), list) and answer_idx < len(q.get("options", [])) else ""
        quiz_html += f"""
        <div class="bg-bg-card border border-border rounded-2xl p-5 quiz-item" id="quiz-{i}" data-selected="">
            <div class="flex items-start gap-3 mb-4">
                <span class="w-6 h-6 rounded-lg bg-accent-bg flex items-center justify-center text-xs font-bold text-fg flex-shrink-0">{i+1}</span>
                <p class="text-sm font-medium text-fg">{q.get("question", "")}</p>
            </div>
            <div class="space-y-2">{opts_html}</div>
            <div class="mt-3 p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/10 hidden quiz-explanation">
                <div class="flex items-center gap-2 mb-1">
                    <svg class="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 13l4 4L19 7"/></svg>
                    <span class="text-xs font-semibold text-emerald-400">Answer: {correct_option}</span>
                </div>
                <p class="text-xs text-fg-muted leading-relaxed">{q.get("explanation", "")}</p>
            </div>
        </div>"""

    return HTMLResponse(f"""
    <div class="space-y-4">
        <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-semibold text-fg">Quiz — {doc['title']}</h3>
            <span class="text-xs text-fg-dim" id="quiz-score"></span>
        </div>
        {quiz_html}
        <div class="flex gap-2 mt-4">
            <button onclick="checkQuizAnswers()" class="px-4 py-2 rounded-xl bg-accent text-accent-text text-sm font-medium hover:opacity-90 transition-opacity">Check Answers</button>
            <button onclick="resetQuiz()" class="px-4 py-2 rounded-xl bg-accent-bg text-fg-muted text-sm font-medium hover:text-fg transition-colors">Reset</button>
        </div>
    </div>
    """)



@router.post("/{doc_id}/study", response_class=HTMLResponse)
async def generate_study(doc_id: str, request: Request = None):
    row = execute_one(
        "SELECT id, title, content_text, summary, entities_json, keywords, study_slides_json FROM documents WHERE id = %s",
        (doc_id,),
    )
    if not row:
        return HTMLResponse("""<div class="text-error text-sm">Document not found</div>""", status_code=404)

    doc = dict(row)
    
    # Check for cached study slides (skip if ?regenerate=true)
    cached = doc.get("study_slides_json")
    if cached and not (request and request.query_params.get("regenerate")):
        if isinstance(cached, str):
            try:
                sections = json.loads(cached)
            except Exception:
                sections = None
        else:
            sections = cached
        if sections:
            title = doc.get("title", "")
            study_html = _build_study_slides_html(sections)
            return _build_study_response(study_html, len(sections), title, doc_id, True)

    raw_text = doc.get("content_text", "")
    summary = doc.get("summary", "")
    title = doc.get("title", "")

    # Build context from entities and keywords if available
    entities = doc.get("entities_json", {})
    if isinstance(entities, str):
        try:
            entities = json.loads(entities)
        except Exception:
            entities = {}
    keywords = doc.get("keywords", [])
    if isinstance(keywords, str):
        try:
            keywords = json.loads(keywords)
        except Exception:
            keywords = []

    topics = entities.get("topics", [])
    people = entities.get("people", [])
    orgs = entities.get("organizations", [])
    dates_list = entities.get("dates", [])

    # Smart content strategy: for large documents with a good AI summary,
    # send the structured summary + entities instead of raw text.
    # This drastically reduces input tokens while preserving all key information.
    has_good_summary = summary and summary != "AI processing skipped (API unavailable)"
    content_length = len(raw_text)

    if content_length > 5000 and has_good_summary:
        # Large document with AI-processed summary - use rich structured context
        entity_lines = []
        if topics:
            entity_lines.append(f"Key Topics: {', '.join(topics[:12])}")
        if people:
            entity_lines.append(f"People/Figures: {', '.join(people[:8])}")
        if orgs:
            entity_lines.append(f"Organizations: {', '.join(orgs[:8])}")
        if dates_list:
            entity_lines.append(f"Timeline/Periods: {', '.join(dates_list[:8])}")
        if keywords:
            entity_lines.append(f"Keywords: {', '.join(keywords[:12])}")
        entity_context = "\n".join(entity_lines)

        content_section = f"""Document Summary (AI-generated):
{summary}

Key Concepts & Entities:
{entity_context}

(Note: This is a large document. The summary above captures all essential information. Build the study guide from this structured knowledge.)"""
    else:
        # Small document or no summary available - use raw text (truncated safely)
        raw_snippet = raw_text[:8000]
        context_line = f"Key topics: {', '.join(topics[:6])}. Keywords: {', '.join(keywords[:6] if isinstance(keywords, list) else [])}." if topics or keywords else ""
        content_section = f"""Summary: {summary[:500]}
{context_line}

Full content:
{raw_snippet}"""

    study_prompt = f"""You are an expert teacher creating an interactive slideshow lesson. Create a step-by-step study guide based on the following document.

Document title: {title}

{content_section}

Create a structured lesson plan in JSON format. Return ONLY a JSON array of objects, each representing a slide:
[
  {{
    "section": "Section title (e.g., Introduction, Key Concepts, Deep Dive, etc.)",
    "content": "Teaching content for this slide (2-3 paragraphs, conversational tone, explain like you're teaching a student)",
    "visual_type": "diagram|code|none",
    "visual_content": "If visual_type is 'diagram': mermaid diagram code. If 'code': code snippet with language specified. Otherwise empty string.",
    "quiz": {{
      "question": "Multiple choice question about this section",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": 0,
      "explanation": "Why this answer is correct"
    }},
    "key_point": "One key takeaway from this section"
  }}
]

Generate 3-8 slides depending on the depth and complexity of the material. Cover all important concepts without being overly verbose. Make it engaging and educational. Start simple, then go deeper.
For every 2nd or 3rd slide, include a quiz question.
For technical topics, use visual_type='code' with actual code examples.
For conceptual topics, use visual_type='diagram' with mermaid syntax diagrams.

Example mermaid diagram:
graph TD
    A[Concept 1] --> B[Concept 2]
    B --> C[Concept 3]

Example code block:
```python
def example():
    print("Hello World")
```"""

    from app.services.ai_client import chat_completion as _ai_chat

    generation_failed = False
    try:
        result = _ai_chat(
            messages=[{"role": "user", "content": study_prompt}],
            temperature=0.5,
            max_tokens=4000,
        )
        content = result["content"]
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
        sections = json.loads(content)
    except Exception as e:
        print(f"[STUDY] Generation failed: {e}")
        generation_failed = True
        sections = [
            {"section": "Study Guide Unavailable", "content": "The AI study module could not generate a lesson at this time. Please try again later.", "visual_hint": "", "key_point": "Try again when the AI service is available."}
        ]

    # Only cache successful generations (don't cache the fallback error)
    if not generation_failed:
        try:
            execute(
                "UPDATE documents SET study_slides_json = %s WHERE id = %s",
                (json.dumps(sections), doc_id)
            )
        except Exception:
            pass

    study_html = _build_study_slides_html(sections)
    return _build_study_response(study_html, len(sections), title, doc_id, False)


def _build_study_slides_html(sections):
    """Build HTML for study slides from sections list."""
    study_html = ""
    for i, s in enumerate(sections):
        section_title = s.get("section", f"Section {i+1}")
        section_content = s.get("content", "")
        visual_type = s.get("visual_type", "none")
        visual_content = s.get("visual_content", "")
        key_point = s.get("key_point", "")
        quiz = s.get("quiz", {})

        # Visual block
        visual_block = ""
        if visual_type == "diagram" and visual_content:
            visual_block = f"""
            <div class="mt-4 p-4 rounded-xl bg-bg-input border border-border overflow-auto">
                <div class="mermaid">{visual_content}</div>
            </div>"""
        elif visual_type == "code" and visual_content:
            lang = "text"
            code = visual_content
            if visual_content.startswith("```"):
                lines = visual_content.split("\n")
                lang = lines[0].replace("```", "") or "text"
                code = "\n".join(lines[1:-1]) if len(lines) > 2 else visual_content
            visual_block = f"""
            <div class="mt-4 rounded-xl overflow-hidden border border-border">
                <div class="bg-bg-raised px-4 py-2 text-xs text-fg-dim font-mono border-b border-border">{lang}</div>
                <pre class="p-4 text-sm text-fg-muted overflow-x-auto"><code>{code}</code></pre>
            </div>"""

        # Quiz block (if exists)
        quiz_block = ""
        if quiz and quiz.get("question"):
            opts_html = "".join(
                f'<div class="quiz-option flex items-center gap-3 p-3 rounded-xl border border-border hover:border-fg-muted/30 cursor-pointer transition-colors" data-correct="{str(j == quiz.get("answer", 0)).lower()}" onclick="selectStudyQuiz(this,{i})"><span class="w-5 h-5 rounded-full border-2 border-border flex-shrink-0 flex items-center justify-center"><span class="w-2 h-2 rounded-full bg-emerald-400 hidden quiz-dot"></span></span><span class="text-sm text-fg-muted">{o}</span></div>'
                for j, o in enumerate(quiz.get("options", []))
            )
            answer_idx = quiz.get("answer", 0)
            opts = quiz.get("options", ["", "", "", ""])
            correct_option = opts[answer_idx] if isinstance(opts, list) and answer_idx < len(opts) else ""
            quiz_block = f"""
            <div class="mt-6 p-5 rounded-xl bg-violet-500/5 border border-violet-500/10 study-quiz" id="study-quiz-{i}" data-selected="">
                <h5 class="text-sm font-semibold text-fg mb-3 flex items-center gap-2">
                    <svg class="w-4 h-4 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    Quick Check
                </h5>
                <p class="text-sm text-fg mb-4">{quiz.get("question", "")}</p>
                <div class="space-y-2">{opts_html}</div>
                <div class="mt-3 p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/10 hidden quiz-explanation">
                    <div class="flex items-center gap-2 mb-1">
                        <svg class="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 13l4 4L19 7"/></svg>
                        <span class="text-xs font-semibold text-emerald-400">Answer: {correct_option}</span>
                    </div>
                    <p class="text-xs text-fg-muted leading-relaxed">{quiz.get("explanation", "")}</p>
                </div>
            </div>"""

        study_html += f"""
        <div class="slide-content" id="slide-{i}" style="display: {'block' if i == 0 else 'none'};">
            <div class="bg-bg-card border border-border rounded-2xl p-6 lg:p-8">
                <div class="flex items-start gap-4 mb-6">
                    <span class="w-10 h-10 rounded-xl bg-accent-bg flex items-center justify-center text-base font-bold text-fg flex-shrink-0">{i+1}</span>
                    <div class="flex-1">
                        <h3 class="text-xl font-bold text-fg mb-4">{section_title}</h3>
                        <div class="prose prose-invert max-w-none">
                            <p class="text-base text-fg-muted leading-relaxed whitespace-pre-line">{section_content}</p>
                        </div>
                        {visual_block}
                        {'<div class="mt-6 p-4 rounded-xl bg-amber-500/5 border border-amber-500/10 flex items-start gap-3"><svg class="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg><div><span class="text-sm text-amber-300 font-semibold block mb-1">Key Point</span><span class="text-sm text-fg-muted">' + key_point + '</span></div></div>' if key_point else ''}
                        {quiz_block}
                    </div>
                </div>
            </div>
        </div>"""
    return study_html


def _build_study_response(study_html, total_slides, title, doc_id, from_cache=False):
    """Build the full study HTML response with navigation, script, and completion modal."""
    cache_label = ' (cached)' if from_cache else ''
    return HTMLResponse(f"""
    <div class="space-y-4">
        <div class="flex items-center justify-between mb-4">
            <div>
                <h3 class="text-lg font-bold text-fg">AI Study Guide{cache_label}</h3>
                <p class="text-sm text-fg-dim mt-0.5">{total_slides} slides generated from "{title}"</p>
            </div>
            <div class="flex items-center gap-3">
                <span class="text-sm text-fg-dim" id="slide-counter">Slide 1 of {total_slides}</span>
                <button hx-post="/api/documents/{doc_id}/study?regenerate=true" hx-target="#study-content" hx-swap="innerHTML"
                    hx-disabled-elt="this" hx-indicator="#regenerate-spinner"
                    class="px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 transition-colors flex items-center gap-1.5 disabled:opacity-50">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                    Regenerate
                    <span id="regenerate-spinner" class="htmx-indicator w-3 h-3 border-2 border-amber-400/30 border-t-amber-400 rounded-full animate-spin"></span>
                </button>
            </div>
        </div>
        
        <!-- Progress Bar -->
        <div class="w-full bg-bg-input rounded-full h-2 mb-6">
            <div id="progress-bar" class="bg-emerald-500 h-2 rounded-full transition-all duration-300" style="width: {100/total_slides}%"></div>
        </div>
        
        {study_html}
        
        <!-- Navigation Controls -->
        <div class="flex items-center justify-between mt-6 sticky bottom-0 bg-bg/95 backdrop-blur-md p-4 rounded-xl border border-border">
            <button onclick="prevSlide()" id="prev-btn" class="px-4 py-2 rounded-xl bg-accent-bg text-fg text-sm font-medium hover:bg-accent-bg/70 transition-colors disabled:opacity-50 disabled:cursor-not-allowed" disabled>
                ← Previous
            </button>
            <button onclick="markSlideComplete()" id="complete-btn" class="px-4 py-2 rounded-xl bg-emerald-500/10 text-emerald-400 text-sm font-medium hover:bg-emerald-500/20 transition-colors">
                ✓ Mark Complete
            </button>
            <button onclick="handleNextOrFinish()" id="next-btn" class="px-4 py-2 rounded-xl bg-accent text-accent-text text-sm font-medium hover:opacity-90 transition-opacity">
                Next →
            </button>
        </div>
    </div>
    
    <!-- Completion Modal -->
    <div id="completion-modal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-bg/60 backdrop-blur-sm">
        <div class="bg-bg-card border border-border rounded-2xl p-8 w-full max-w-lg mx-4 text-center">
            <div class="w-16 h-16 rounded-2xl bg-emerald-500/10 flex items-center justify-center mx-auto mb-4">
                <svg class="w-8 h-8 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 13l4 4L19 7"/></svg>
            </div>
            <h3 class="text-xl font-bold text-fg mb-2">Study Complete!</h3>
            <p class="text-fg-muted text-sm mb-6">Great job mastering this topic. What would you like to do next?</p>
            <div class="space-y-3">
                <button onclick="studyNextDocument()" class="w-full px-4 py-3 rounded-xl bg-accent text-accent-text text-sm font-medium hover:opacity-90 transition-opacity flex items-center justify-center gap-2">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>
                    Study Next Document
                </button>
                <button hx-post="/api/documents/{doc_id}/ai-continue" hx-swap="none" hx-indicator="#ai-continue-spinner"
                    class="w-full px-4 py-3 rounded-xl bg-violet-500/10 text-violet-400 text-sm font-medium hover:bg-violet-500/20 transition-colors flex items-center justify-center gap-2">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg>
                    AI Knows More
                    <span id="ai-continue-spinner" class="htmx-indicator w-3.5 h-3.5 border-2 border-violet-400/30 border-t-violet-400 rounded-full animate-spin"></span>
                </button>
                <a href="/study" class="block w-full px-4 py-3 rounded-xl bg-accent-bg text-fg-muted text-sm font-medium hover:bg-accent-bg/70 transition-colors">
                    Back to Library
                </a>
            </div>
        </div>
    </div>
    
    <script>
        let currentSlide = 0;
        const totalSlides = {total_slides};
        const completedSlides = new Set();
        
        function showSlide(index) {{
            document.querySelectorAll('.slide-content').forEach(s => s.style.display = 'none');
            document.getElementById('slide-' + index).style.display = 'block';
            document.getElementById('slide-counter').textContent = `Slide ${{index + 1}} of ${{totalSlides}}`;
            const progress = ((index + 1) / totalSlides) * 100;
            document.getElementById('progress-bar').style.width = progress + '%';
            document.getElementById('prev-btn').disabled = index === 0;
            
            // Update next/finish button
            const nextBtn = document.getElementById('next-btn');
            if (index === totalSlides - 1) {{
                nextBtn.textContent = 'Finish \u2713';
                nextBtn.classList.add('bg-emerald-500', 'text-white');
            }} else {{
                nextBtn.textContent = 'Next \u2192';
                nextBtn.classList.remove('bg-emerald-500', 'text-white');
            }}
            
            currentSlide = index;
            
            if (typeof mermaid !== 'undefined') {{
                const slideEl = document.getElementById('slide-' + index);
                slideEl.querySelectorAll('.mermaid').forEach(async (el) => {{
                    try {{ await mermaid.run({{ nodes: [el] }}); }} catch (e) {{ el.style.display = 'none'; }}
                }});
            }}
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}
        
        function handleNextOrFinish() {{
            if (currentSlide >= totalSlides - 1) {{
                showCompletionModal();
            }} else {{
                showSlide(currentSlide + 1);
            }}
        }}
        
        function prevSlide() {{ if (currentSlide > 0) showSlide(currentSlide - 1); }}
        
        function showCompletionModal() {{
            fetch('/api/documents/{doc_id}/study-complete', {{ method: 'POST' }});
            document.getElementById('completion-modal').classList.remove('hidden');
        }}
        
        async function studyNextDocument() {{
            const resp = await fetch('/api/documents/study-next');
            const url = await resp.text();
            window.location.href = url || '/study';
        }}
        
        function markSlideComplete() {{
            completedSlides.add(currentSlide);
            const btn = document.getElementById('complete-btn');
            btn.textContent = '\u2713 Completed';
            btn.classList.remove('bg-emerald-500/10', 'text-emerald-400');
            btn.classList.add('bg-emerald-500/20', 'text-emerald-300');
        }}
        
        function selectStudyQuiz(el, qIdx) {{
            var item = el.closest('.study-quiz');
            item.querySelectorAll('.quiz-option').forEach(function(o) {{
                o.classList.remove('border-fg-muted/50', 'quiz-option-selected');
                o.querySelector('.quiz-dot').classList.add('hidden');
            }});
            el.classList.add('quiz-option-selected', 'border-fg-muted/50');
            el.querySelector('.quiz-dot').classList.remove('hidden');
            item.dataset.selected = el.dataset.correct;
            setTimeout(() => {{ item.querySelector('.quiz-explanation').classList.remove('hidden'); }}, 300);
        }}
        
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'ArrowRight') handleNextOrFinish();
            if (e.key === 'ArrowLeft') prevSlide();
            if (e.key === ' ') {{ e.preventDefault(); markSlideComplete(); }}
        }});
    </script>
    """)



@router.get("/{doc_id}/study-page", response_class=HTMLResponse)
async def study_page(request: Request, doc_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    from app.templating import templates
    theme = theme_from_request(request)
    row = execute_one(
        "SELECT id, title, source_type, word_count, summary FROM documents WHERE id = %s AND user_id = %s",
        (doc_id, user["id"]),
    )
    if not row:
        return HTMLResponse("Document not found", status_code=404)
    doc = dict(row)
    reading_time = max(1, (doc.get("word_count", 0) or 0) // 200)
    return templates.TemplateResponse(
        "study.html",
        {"request": request, "user": user, "theme": theme, "doc": doc, "reading_time": reading_time, "sidebar_active": "study"},
    )


@router.post("/{doc_id}/favorite")
async def toggle_favorite(request: Request, doc_id: str):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)
    
    row = execute_one(
        "SELECT is_favorite FROM documents WHERE id = %s AND user_id = %s",
        (doc_id, user["id"])
    )
    if not row:
        return HTMLResponse("Document not found", status_code=404)
    
    new_status = not row["is_favorite"]
    execute(
        "UPDATE documents SET is_favorite = %s WHERE id = %s",
        (new_status, doc_id)
    )
    
    response = HTMLResponse(content="")
    response.headers["HX-Refresh"] = "true"
    return response


@router.post("/{doc_id}/category")
async def set_category(request: Request, doc_id: str, category: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)
    
    execute(
        "UPDATE documents SET category = %s WHERE id = %s AND user_id = %s",
        (category if category else None, doc_id, user["id"])
    )
    
    response = HTMLResponse(content="")
    response.headers["HX-Refresh"] = "true"
    return response


# ===== STUDY PROGRESS ENDPOINTS =====

@router.post("/{doc_id}/record-study", response_class=HTMLResponse)
async def record_study(request: Request, doc_id: str):
    """Record a study session for spaced repetition tracking."""
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)

    user_id = user["id"]
    today = date.today()

    existing = execute_one(
        "SELECT study_count, review_interval FROM study_progress WHERE user_id = %s AND document_id = %s",
        (user_id, doc_id)
    )

    intervals = [1, 3, 7, 14, 30]

    if existing:
        new_count = existing["study_count"] + 1
        current_interval = existing["review_interval"] or 0
        if current_interval in intervals:
            idx = intervals.index(current_interval)
            next_idx = min(idx + 1, len(intervals) - 1)
        else:
            next_idx = 0
        new_interval = intervals[next_idx]

        if new_count >= 5:
            mastery = "mastered"
        elif new_count >= 3:
            mastery = "reviewing"
        else:
            mastery = "learning"

        next_review = today + timedelta(days=new_interval)

        execute(
            """UPDATE study_progress
               SET study_count = %s, last_studied = now(), next_review = %s,
                   review_interval = %s, mastery = %s, updated_at = now()
               WHERE user_id = %s AND document_id = %s""",
            (new_count, next_review, new_interval, mastery, user_id, doc_id)
        )
    else:
        new_interval = intervals[0]
        next_review = today + timedelta(days=new_interval)
        execute(
            """INSERT INTO study_progress (user_id, document_id, study_count, last_studied,
               next_review, review_interval, mastery)
               VALUES (%s, %s, 1, now(), %s, %s, 'learning')""",
            (user_id, doc_id, next_review, new_interval)
        )

    stats = execute_one(
        "SELECT current_streak, longest_streak, last_study_date, total_sessions FROM user_study_stats WHERE user_id = %s",
        (user_id,)
    )

    if stats:
        last_date = stats["last_study_date"]
        new_streak = stats["current_streak"]
        new_total = stats["total_sessions"] + 1

        if last_date:
            if hasattr(last_date, 'strftime'):
                last_date_val = last_date
            else:
                last_date_val = last_date

            if last_date_val == today:
                pass
            elif last_date_val == today - timedelta(days=1):
                new_streak += 1
            else:
                new_streak = 1
        else:
            new_streak = 1

        longest = max(stats["longest_streak"] or 0, new_streak)

        execute(
            """UPDATE user_study_stats
               SET current_streak = %s, longest_streak = %s, last_study_date = %s,
                   total_sessions = %s, updated_at = now()
               WHERE user_id = %s""",
            (new_streak, longest, today, new_total, user_id)
        )
    else:
        execute(
            """INSERT INTO user_study_stats (user_id, current_streak, longest_streak,
               last_study_date, total_sessions)
               VALUES (%s, 1, 1, %s, 1)""",
            (user_id, today)
        )

    return HTMLResponse(content="")


@router.post("/{doc_id}/study-complete", response_class=HTMLResponse)
async def study_complete(request: Request, doc_id: str):
    """Mark a study session as completed."""
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)

    execute(
        "UPDATE study_progress SET completed = TRUE, updated_at = now() WHERE user_id = %s AND document_id = %s",
        (user["id"], doc_id)
    )
    return HTMLResponse(content="")


@router.post("/{doc_id}/ai-continue", response_class=HTMLResponse)
async def ai_continue_study(request: Request, doc_id: str):
    """Generate an AI follow-up lesson. Redirects to existing child if already generated."""
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)

    # Check if a follow-up already exists for this document
    existing_child = execute_one(
        "SELECT id FROM documents WHERE parent_document_id = %s AND user_id = %s",
        (doc_id, user["id"])
    )
    if existing_child:
        response = HTMLResponse(content="")
        response.headers["HX-Redirect"] = f"/api/documents/{existing_child['id']}/study-page?from=ai-continue"
        return response

    doc = execute_one(
        "SELECT id, title, content_text, summary, entities_json, keywords FROM documents WHERE id = %s AND user_id = %s",
        (doc_id, user["id"])
    )
    if not doc:
        return HTMLResponse("Document not found", status_code=404)

    doc = dict(doc)
    text = doc.get("content_text", "")[:8000]
    summary = doc.get("summary", "")
    title = doc.get("title", "")

    entities = doc.get("entities_json", {})
    if isinstance(entities, str):
        try:
            entities = json.loads(entities)
        except Exception:
            entities = {}
    keywords = doc.get("keywords", [])
    if isinstance(keywords, str):
        try:
            keywords = json.loads(keywords)
        except Exception:
            keywords = []

    topics = entities.get("topics", [])
    topic_str = ", ".join(topics[:5]) if topics else title
    kw_str = ", ".join(keywords[:5]) if keywords else ""

    ai_prompt = f"""You are an expert educator designing a structured learning path. A student just finished studying:

Document: "{title}"
Summary: {summary[:500]}
Topics covered: {topic_str}
Keywords: {kw_str}

Content studied:
{text[:5000]}

CRITICAL: Create the NEXT logical lesson in a sequential learning path. DO NOT jump to advanced topics. The next lesson must build directly on what was just learned. If the student just learned basics (e.g., Hello World, variables, basic syntax), teach the next foundational concept (e.g., data types, conditionals, loops). Only advance to intermediate/advanced topics if the current material is already at that level.

Create a follow-up lesson. Return ONLY valid JSON:
{{
  "new_title": "Concise, descriptive title of the specific next topic",
  "content": "A detailed lesson (600-1200 words). Use examples, analogies, and a conversational teaching tone. Build on concepts from the previous lesson.",
  "summary": "A 2-3 sentence summary of what this lesson covers",
  "key_points": ["Key point 1", "Key point 2", "Key point 3", "Key point 4", "Key point 5"]
}}"""

    from app.services.ai_client import chat_completion as _ai_chat

    try:
        result = _ai_chat(
            messages=[{"role": "user", "content": ai_prompt}],
            temperature=0.6,
            max_tokens=2000,
        )
        content = result["content"]
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
        lesson = json.loads(content)
    except Exception:
        lesson = {
            "new_title": f"Next: Continuing {title}",
            "content": "The AI service is currently unavailable. Please try generating a follow-up lesson later.",
            "summary": "Follow-up lesson generation was unavailable.",
            "key_points": ["Retry when the AI service is back online"]
        }

    import uuid as _uuid
    new_doc_id = str(_uuid.uuid4())
    new_title = lesson.get("new_title", f"Continuing: {title}")
    new_content = lesson.get("content", "")
    new_summary = lesson.get("summary", "")
    new_keywords = lesson.get("key_points", [])

    execute(
        """INSERT INTO documents (id, user_id, title, source_type, content_text, summary, keywords, word_count, parent_document_id)
           VALUES (%s, %s, %s, 'ai_generated', %s, %s, %s, %s, %s)""",
        (new_doc_id, user["id"], new_title, new_content,
         new_summary, new_keywords, len(new_content.split()), doc_id)
    )

    response = HTMLResponse(content="")
    response.headers["HX-Redirect"] = f"/api/documents/{new_doc_id}/study-page"
    return response


@router.get("/study-next", response_class=HTMLResponse)
async def study_next_document(request: Request):
    """Return the URL of the next unstudied document, or the first document."""
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)

    row = execute_one(
        """SELECT d.id FROM documents d
           LEFT JOIN study_progress sp ON d.id = sp.document_id AND sp.user_id = %s
           WHERE d.user_id = %s AND sp.id IS NULL
           ORDER BY d.created_at ASC LIMIT 1""",
        (user["id"], user["id"])
    )

    if not row:
        row = execute_one(
            """SELECT d.id FROM documents d
               JOIN study_progress sp ON d.id = sp.document_id AND sp.user_id = %s
               WHERE d.user_id = %s
               ORDER BY sp.next_review ASC NULLS LAST LIMIT 1""",
            (user["id"], user["id"])
        )

    if row:
        return HTMLResponse(content=f"/api/documents/{row['id']}/study-page")
    return HTMLResponse(content="/study")
