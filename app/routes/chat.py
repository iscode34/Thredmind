"""
Chat route: RAG-powered AI chat with semantic search and knowledge graph integration.
Uses local embeddings (fastembed/ONNX) for retrieval and the AI provider rotation for generation.
"""
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies import get_current_user, theme_from_request
from app.services.db_client import execute, execute_one
from app.services.embedding_service import search_chunks

router = APIRouter()

# ============================================================
# Pages
# ============================================================

@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    from app.templating import templates
    theme = theme_from_request(request)

    # Load existing sessions
    sessions = execute(
        "SELECT id, title, updated_at, is_pinned FROM chat_sessions WHERE user_id = %s ORDER BY is_pinned DESC, updated_at DESC LIMIT 20",
        (user["id"],)
    ) or []
    sessions_list = []
    for s in sessions:
        sd = dict(s)
        if sd.get("updated_at"):
            sd["updated_at"] = sd["updated_at"].strftime("%b %d")
        sessions_list.append(sd)

    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "user": user, "theme": theme,
            "sidebar_active": "chat", "sessions": sessions_list
        }
    )



# ============================================================
# Semantic Search
# ============================================================

@router.post("/chat/search", response_class=HTMLResponse)
async def semantic_search(request: Request, query: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)

    if not query.strip():
        return HTMLResponse("""<div class="text-fg-dim text-sm p-4">Enter a search query to find relevant documents.</div>""")

    try:
        results = search_chunks(query.strip(), user["id"], limit=5)
    except Exception as e:
        return HTMLResponse(f"""<div class="text-error text-sm p-4">Search failed: {str(e)}</div>""")

    if not results:
        return HTMLResponse("""<div class="text-fg-dim text-sm p-4">No relevant documents found. Try a different query.</div>""")

    items = ""
    for r in results:
        source_icon = {"pdf": "text-red-400", "docx": "text-blue-400", "url": "text-sky-400", "ai_generated": "text-violet-400", "txt": "text-emerald-400", "md": "text-emerald-400"}.get(r.get("source_type", ""), "text-fg-dim")
        items += f"""
        <a href="/api/documents/{r['id']}" class="flex items-start gap-3 p-3 rounded-xl hover:bg-accent-bg transition-colors group">
            <div class="w-8 h-8 rounded-lg bg-accent-bg flex items-center justify-center flex-shrink-0 mt-0.5">
                <svg class="w-4 h-4 {source_icon}" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
            </div>
            <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-fg truncate group-hover:text-fg transition-colors">{r['title']}</p>
                <p class="text-xs text-fg-dim mt-0.5 line-clamp-2">{r.get('snippet', r.get('summary', ''))[:200]}</p>
                <div class="flex items-center gap-2 mt-1.5">
                    <span class="text-[10px] text-fg-dim uppercase">{r.get('source_type', '')}</span>
                    <span class="px-1.5 py-0.5 rounded-md bg-emerald-500/10 text-[10px] text-emerald-400 font-medium">{r.get('similarity', 0)}% match</span>
                </div>
            </div>
        </a>"""

    return HTMLResponse(f"""<div class="divide-y divide-border">{items}</div>""")


# ============================================================
# RAG Chat
# ============================================================

@router.post("/chat/message", response_class=HTMLResponse)
async def chat_message(request: Request, message: str = Form(...), session_id: str = Form("")):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)

    message = message.strip()
    if not message:
        return HTMLResponse("")

    user_id = user["id"]

    # Create or get session
    if not session_id:
        session_id = str(uuid.uuid4())
        execute(
            "INSERT INTO chat_sessions (id, user_id, title) VALUES (%s, %s, %s)",
            (session_id, user_id, message[:80])
        )

    # Save user message
    execute(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s)",
        (session_id, "user", message)
    )

    # --- RAG Pipeline ---
    # Step 1: Semantic search for relevant documents
    context_chunks = []
    citations = []
    try:
        results = search_chunks(message, user_id, limit=5)
        for r in results:
            sim = r.get("similarity", 0)
            if sim > 10:  # Include all relevant documents (lower threshold)
                context_chunks.append(f"### {r['title']}\n{r.get('snippet', '')}")
                citations.append({"id": r["id"], "title": r["title"], "similarity": sim})
    except Exception:
        pass

    # Step 2: Knowledge graph context (query user's content graph from DB)
    graph_context = _get_graph_context(message, user_id)

    # Step 3: Build RAG prompt
    rag_context = ""
    if context_chunks:
        rag_context = "Relevant documents from your knowledge base:\n\n" + "\n\n---\n\n".join(context_chunks[:3])

    if graph_context:
        rag_context += f"\n\nKnowledge Graph Connections:\n{graph_context}"

    system_prompt = """You are ThredMind, an AI knowledge assistant. Answer questions based on the user's personal knowledge base.
- Use the provided document context to give accurate, specific answers.
- Cite which document(s) your information comes from.
- If the context doesn't contain the answer, say so honestly and suggest what the user might upload or search for.
- Keep answers concise but thorough. Use examples when helpful.
- The knowledge graph shows how concepts connect — mention related topics when relevant."""

    user_prompt = message
    if rag_context:
        user_prompt = f"""Context from your knowledge base:

{rag_context}

User question: {message}

Answer the question using the context above. Mention which documents you used."""

    # Step 4: Call AI
    from app.services.ai_client import chat_completion as _ai_chat

    try:
        result = _ai_chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.5,
            max_tokens=1500,
        )
        answer = result["content"]
        provider = result.get("provider", "AI")
    except Exception as e:
        answer = f"I'm having trouble connecting to the AI service right now. Please try again in a moment.\n\nError: {str(e)[:200]}"
        provider = "error"

    # Save AI response
    execute(
        "INSERT INTO chat_messages (session_id, role, content, citations_json) VALUES (%s, %s, %s, %s)",
        (session_id, "assistant", answer, json.dumps(citations) if citations else None)
    )

    # Update session timestamp
    execute(
        "UPDATE chat_sessions SET updated_at = now() WHERE id = %s",
        (session_id,)
    )

    # Build citation HTML
    citation_html = ""
    if citations:
        cite_items = ""
        for c in citations[:3]:
            cite_items += f"""
            <a href="/api/documents/{c['id']}" class="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-accent-bg hover:bg-accent-bg/70 transition-colors text-xs">
                <svg class="w-3 h-3 text-fg-dim" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                <span class="text-fg-muted truncate max-w-[140px]">{c['title']}</span>
                <span class="text-emerald-400">{c['similarity']}%</span>
            </a>"""
        citation_html = f"""
        <div class="mt-3 pt-3 border-t border-border">
            <p class="text-[10px] text-fg-dim uppercase tracking-widest mb-2">Sources</p>
            <div class="flex flex-wrap gap-1.5">{cite_items}</div>
        </div>"""

    # Return both the user message and AI response as HTML
    return HTMLResponse(f"""
    <div class="chat-message user-message flex justify-end mb-4" id="msg-user-{session_id}">
        <div class="max-w-[80%] bg-accent-bg rounded-2xl rounded-br-md px-4 py-3">
            <p class="text-sm text-fg whitespace-pre-wrap">{message}</p>
        </div>
    </div>
    <div class="chat-message ai-message flex gap-3 mb-4" id="msg-ai-{session_id}">
        <div class="w-7 h-7 rounded-lg bg-violet-500/10 flex items-center justify-center flex-shrink-0 mt-0.5">
            <svg class="w-3.5 h-3.5 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg>
        </div>
        <div class="flex-1 min-w-0">
            <div class="bg-bg-card border border-border rounded-2xl rounded-bl-md px-4 py-3">
                <p class="text-sm text-fg-muted whitespace-pre-wrap leading-relaxed">{answer}</p>
                {citation_html}
            </div>
            <p class="text-[10px] text-fg-dim mt-1 ml-1">via {provider}</p>
        </div>
    </div>
    <script>
        // Scroll to the new AI message
        document.getElementById('msg-ai-{session_id}').scrollIntoView({{ behavior: 'smooth', block: 'end' }});
        // Store the session ID in the hidden input for subsequent messages
        var sidInput = document.getElementById('chat-session-id');
        if (sidInput && !sidInput.value) sidInput.value = '{session_id}';
    </script>
    """)


# ============================================================
# Session Management
# ============================================================

@router.get("/chat/sessions/{session_id}", response_class=HTMLResponse)
async def load_session(request: Request, session_id: str):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)

    messages = execute(
        "SELECT role, content, citations_json, created_at FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC",
        (session_id,)
    ) or []

    html = ""
    for m in messages:
        msg = dict(m)
        if msg["role"] == "user":
            html += f"""
            <div class="chat-message user-message flex justify-end mb-4">
                <div class="max-w-[80%] bg-accent-bg rounded-2xl rounded-br-md px-4 py-3">
                    <p class="text-sm text-fg whitespace-pre-wrap">{msg['content']}</p>
                </div>
            </div>"""
        else:
            citations = msg.get("citations_json")
            if isinstance(citations, str):
                try:
                    citations = json.loads(citations)
                except Exception:
                    citations = None

            cite_html = ""
            if citations:
                cite_items = ""
                for c in citations[:3]:
                    cite_items += f"""
                    <a href="/api/documents/{c['id']}" class="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-accent-bg hover:bg-accent-bg/70 transition-colors text-xs">
                        <svg class="w-3 h-3 text-fg-dim" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                        <span class="text-fg-muted truncate max-w-[140px]">{c['title']}</span>
                        <span class="text-emerald-400">{c['similarity']}%</span>
                    </a>"""
                cite_html = f"""
                <div class="mt-3 pt-3 border-t border-border">
                    <p class="text-[10px] text-fg-dim uppercase tracking-widest mb-2">Sources</p>
                    <div class="flex flex-wrap gap-1.5">{cite_items}</div>
                </div>"""

            html += f"""
            <div class="chat-message ai-message flex gap-3 mb-4">
                <div class="w-7 h-7 rounded-lg bg-violet-500/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <svg class="w-3.5 h-3.5 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg>
                </div>
                <div class="flex-1 min-w-0">
                    <div class="bg-bg-card border border-border rounded-2xl rounded-bl-md px-4 py-3">
                        <p class="text-sm text-fg-muted whitespace-pre-wrap leading-relaxed">{msg['content']}</p>
                        {cite_html}
                    </div>
                </div>
            </div>"""

    return HTMLResponse(f"""<div id="chat-messages" class="flex-1 overflow-y-auto p-4 lg:p-6 space-y-0">{html}</div>
    <script>
        var container = document.getElementById('chat-messages');
        container.scrollTop = container.scrollHeight;
        var sidInput = document.getElementById('chat-session-id');
        if (sidInput) sidInput.value = '{session_id}';
    </script>""")


@router.post("/chat/new-session", response_class=HTMLResponse)
async def new_session(request: Request):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)
    # Return empty chat + reset session ID
    return HTMLResponse("""
    <div id="chat-messages" class="flex-1 overflow-y-auto p-4 lg:p-6">
        <div class="flex flex-col items-center justify-center h-full text-center pt-20">
            <div class="w-16 h-16 rounded-2xl bg-violet-500/10 flex items-center justify-center mb-4">
                <svg class="w-8 h-8 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg>
            </div>
            <h3 class="text-lg font-bold text-fg mb-2">ThredMind Chat</h3>
            <p class="text-fg-dim text-sm max-w-sm">Ask questions about your documents. I'll search your knowledge base and use AI to answer.</p>
        </div>
    </div>
    <script>
        document.getElementById('chat-session-id').value = '';
        // Reload the session sidebar
        htmx.ajax('GET', '/chat/sessions-sidebar', '#sessions-list');
    </script>
    """)


@router.get("/chat/sessions-sidebar", response_class=HTMLResponse)
async def sessions_sidebar(request: Request):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("")

    sessions = execute(
        "SELECT id, title, updated_at, is_pinned FROM chat_sessions WHERE user_id = %s ORDER BY is_pinned DESC, updated_at DESC LIMIT 20",
        (user["id"],)
    ) or []

    items = ""
    for s in sessions:
        sd = dict(s)
        date_str = sd["updated_at"].strftime("%b %d") if sd.get("updated_at") else ""
        pinned = sd.get("is_pinned", False)
        pin_icon = '&#x2605;' if pinned else '&#x2606;'
        pin_color = 'text-amber-400' if pinned else 'text-fg-dim'
        items += f"""
        <div class="group/session flex items-center gap-1">
            <button onclick="loadSession('{sd['id']}')" class="flex-1 text-left px-3 py-2 rounded-xl hover:bg-accent-bg transition-colors text-sm text-fg-muted hover:text-fg truncate">
                <span class="{pin_color} mr-1 text-xs">{pin_icon}</span>{sd['title'][:45]}
            </button>
            <div class="relative opacity-0 group-hover/session:opacity-100 transition-opacity">
                <button onclick="toggleSessionMenu(event, '{sd['id']}')" class="w-6 h-6 rounded-lg flex items-center justify-center text-fg-dim hover:text-fg hover:bg-accent-bg transition-colors">
                    <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg>
                </button>
                <div id="menu-{sd['id']}" class="hidden absolute right-0 top-7 z-50 bg-bg-card border border-border rounded-xl shadow-2xl py-1 min-w-[130px]">
                    <button onclick="pinSession('{sd['id']}')" class="w-full text-left px-3 py-2 text-xs text-fg-muted hover:text-fg hover:bg-accent-bg transition-colors flex items-center gap-2">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"/></svg>
                        {'Unpin' if pinned else 'Pin'}
                    </button>
                    <button onclick="deleteSession('{sd['id']}')" class="w-full text-left px-3 py-2 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/5 transition-colors flex items-center gap-2">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                        Delete
                    </button>
                </div>
            </div>
        </div>"""

    if not items:
        items = '<p class="text-xs text-fg-dim px-3 py-2">No conversations yet</p>'

    return HTMLResponse(items)


@router.post("/chat/sessions/{session_id}/pin")
async def toggle_pin(request: Request, session_id: str):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)

    session = execute_one("SELECT is_pinned FROM chat_sessions WHERE id = %s AND user_id = %s", (session_id, user["id"]))
    if session:
        new_val = not session["is_pinned"]
        execute("UPDATE chat_sessions SET is_pinned = %s WHERE id = %s", (new_val, session_id))

    return HTMLResponse(content="")


@router.post("/chat/sessions/{session_id}/delete")
async def delete_session(request: Request, session_id: str):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Not authenticated", status_code=401)

    execute("DELETE FROM chat_messages WHERE session_id = %s", (session_id,))
    execute("DELETE FROM chat_sessions WHERE id = %s AND user_id = %s", (session_id, user["id"]))

    return HTMLResponse(content="")


# ============================================================
# Knowledge Graph Helpers
# ============================================================

def _get_graph_context(query: str, user_id: str) -> str:
    """Query the user's content knowledge graph (DB entities/edges) for context."""
    try:
        # 1. Find documents whose title or summary mentions the query
        query_words = query.lower().split()
        doc_conditions = " OR ".join([f"d.title ILIKE %s" for _ in query_words])
        doc_params = [f"%{w}%" for w in query_words]

        matching_docs = execute(
            f"""SELECT d.id, d.title, d.source_type
               FROM documents d
               WHERE ({doc_conditions})
               LIMIT 3""",
            doc_params
        ) or []

        if not matching_docs:
            # Fallback: search by entity/term overlap
            return _get_graph_by_entities(query, user_id)

        doc_ids = [d["id"] for d in matching_docs]
        lines = []

        for doc in matching_docs:
            # 2. Find entities connected to this document
            entities = execute(
                """SELECT e.name, e.type
                   FROM entities e
                   JOIN edges ed ON ed.target_id = e.id
                   WHERE ed.source_id = %s AND ed.source_type = 'document'
                   LIMIT 6""",
                (doc["id"],)
            ) or []

            entity_list = [f"{e['name']} ({e['type']})" for e in entities]
            lines.append(f"- {doc['title']} [{doc['source_type']}]: {', '.join(entity_list) if entity_list else 'no entities'}")

            # 3. Find documents connected via shared entities (cross-document edges)
            connected = execute(
                """SELECT DISTINCT d2.id, d2.title, d2.source_type, ed.relationship, ed.strength
                   FROM edges ed
                   JOIN documents d2 ON d2.id = ed.target_id
                   WHERE ed.source_id = %s
                     AND ed.source_type = 'document'
                     AND ed.target_type = 'document'
                     AND ed.relationship IN ('shares_concepts', 'semantically_similar')
                   ORDER BY ed.strength DESC
                   LIMIT 5""",
                (doc["id"],)
            ) or []

            if connected:
                conn_list = [f"{c['title']} ({c['relationship']}, {float(c['strength'])*100:.0f}%)" for c in connected]
                lines.append(f"  Connected to: {', '.join(conn_list)}")

        if lines:
            return "\n".join(lines)

        return _get_graph_by_entities(query, user_id)
    except Exception:
        return ""


def _get_graph_by_entities(query: str, user_id: str) -> str:
    """Fallback: find context by matching entity names from the query."""
    try:
        query_words = query.lower().split()
        conditions = " OR ".join([f"e.name ILIKE %s" for _ in query_words])
        params = [f"%{w}%" for w in query_words]

        entities = execute(
            f"""SELECT DISTINCT e.name, e.type, COUNT(ed.source_id) as doc_count
               FROM entities e
               JOIN edges ed ON ed.target_id = e.id
               WHERE ({conditions}) AND ed.source_type = 'document'
               GROUP BY e.name, e.type
               ORDER BY doc_count DESC LIMIT 8""",
            params
        ) or []

        if not entities:
            return ""

        lines = ["Matching concepts in your knowledge base:"]
        for e in entities:
            lines.append(f"- {e['name']} ({e['type']}) — appears in {e['doc_count']} document(s)")

        # Also find top-level connections
        cross_links = execute(
            """SELECT d1.title as src_title, d2.title as tgt_title, ed.relationship, ed.strength
               FROM edges ed
               JOIN documents d1 ON d1.id = ed.source_id
               JOIN documents d2 ON d2.id = ed.target_id
               WHERE ed.source_type = 'document'
                 AND ed.target_type = 'document'
               ORDER BY ed.strength DESC LIMIT 5"""
        ) or []

        if cross_links:
            lines.append("\nStrongest cross-document connections:")
            for cl in cross_links:
                lines.append(f"- {cl['src_title']} ↔ {cl['tgt_title']} ({cl['relationship']}, {float(cl['strength'])*100:.0f}%)")

        return "\n".join(lines)
    except Exception:
        return ""
