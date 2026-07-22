"""
Knowledge Graph Service — powers the ThredMind knowledge graph with:
1. Entity extraction from AI-processed documents → entities table
2. Cross-document linking via shared entities, keyword overlap, and semantic similarity
3. Graph query API for Cytoscape.js visualization

Fix log:
- Normalise entity types from plural AI keys to canonical singular (topics→topic, etc.)
- Add UNIQUE constraint on entities (user_id, LOWER(name), type) via upsert logic
- Deduplicate edges before insertion to avoid multi-edge rendering in Cytoscape
- Remove redundant bidirectional edge creation from _link_by_term_overlap
  (graph.html renders edges as undirected; duplicates cause weight inflation)
"""
import json
import uuid
import logging
from app.services.db_client import execute, execute_one

logger = logging.getLogger(__name__)

# Canonical color map — uses SINGULAR type names
ENTITY_COLORS = {
    "topic":        "#10b981",
    "person":       "#3b82f6",
    "organization": "#8b5cf6",
    "date":         "#f59e0b",
    "keyword":      "#ec4899",
    "category":     "#06b6d4",
}

DOC_TYPE_COLORS = {
    "pdf":          "#ef4444",
    "docx":         "#3b82f6",
    "txt":          "#10b981",
    "md":           "#10b981",
    "url":          "#0ea5e9",
    "pptx":         "#f97316",
    "ai_generated": "#8b5cf6",
}

# Map from plural AI-returned entity-type keys → canonical singular names
_ENTITY_TYPE_MAP = {
    "topics":        "topic",
    "topic":         "topic",
    "people":        "person",
    "person":        "person",
    "organizations": "organization",
    "organization":  "organization",
    "org":           "organization",
    "dates":         "date",
    "date":          "date",
    "keyword":       "keyword",
    "keywords":      "keyword",
    "category":      "category",
}


def _normalize_type(raw: str) -> str:
    """Return canonical singular type name."""
    return _ENTITY_TYPE_MAP.get(raw.lower().strip(), raw.lower().strip())


# ============================================================
# Graph Building
# ============================================================

def process_document_for_graph(doc_id: str, user_id: str):
    """Extract entities from a document and create cross-document edges."""
    doc = execute_one(
        "SELECT id, title, source_type, entities_json, keywords, category, summary "
        "FROM documents WHERE id = %s",
        (doc_id,)
    )
    if not doc:
        return
    doc = dict(doc)

    entities_data = doc.get("entities_json") or {}
    if isinstance(entities_data, str):
        try:
            entities_data = json.loads(entities_data)
        except Exception:
            entities_data = {}

    keywords = doc.get("keywords") or []
    if isinstance(keywords, str):
        try:
            keywords = json.loads(keywords)
        except Exception:
            keywords = []

    # Clear edges FROM this document (idempotent)
    execute(
        "DELETE FROM edges WHERE user_id = %s AND source_id = %s AND source_type = 'document'",
        (user_id, doc_id)
    )

    all_terms: list[str] = []

    # 1. Extract named entities from entities_json (plural AI keys → singular canonical)
    for raw_etype, items in entities_data.items():
        if not isinstance(items, list):
            continue
        etype = _normalize_type(raw_etype)
        for name in items[:10]:
            name = str(name).strip()
            if not name or len(name) < 2:
                continue
            name_lower = name.lower()
            eid = _upsert_entity(user_id, name_lower, etype)
            _create_edge(user_id, doc_id, "document", eid, "entity", f"has_{etype}", 0.9)
            all_terms.append(name_lower)

    # 2. Keywords as entities
    for kw in keywords[:10]:
        kw_str = str(kw).strip().lower()
        if not kw_str or len(kw_str) < 2:
            continue
        eid = _upsert_entity(user_id, kw_str, "keyword")
        _create_edge(user_id, doc_id, "document", eid, "entity", "has_keyword", 0.85)
        all_terms.append(kw_str)

    # 3. Category
    category = doc.get("category")
    if category:
        cat = category.strip().lower()
        if cat:
            eid = _upsert_entity(user_id, cat, "category")
            _create_edge(user_id, doc_id, "document", eid, "entity", "in_category", 1.0)
            all_terms.append(cat)

    # 4. Document title as a topic node (for centrality)
    title_clean = doc["title"].strip().lower()[:80]
    if title_clean:
        title_eid = _upsert_entity(user_id, title_clean, "topic")
        _create_edge(user_id, doc_id, "document", title_eid, "entity", "represents", 1.0)

    # Deduplicate terms
    all_terms = list(set(t for t in all_terms if t))
    logger.info(f"KG: {doc_id[:8]} → {len(all_terms)} unique terms extracted")

    # 5. Cross-document linking
    _link_by_term_overlap(user_id, doc_id, all_terms)
    _link_by_semantic_similarity(user_id, doc_id)


def _upsert_entity(user_id: str, name: str, etype: str) -> str:
    """Insert entity if it doesn't exist, return its id."""
    existing = execute_one(
        "SELECT id FROM entities WHERE user_id = %s AND LOWER(name) = %s AND type = %s",
        (user_id, name.lower(), etype)
    )
    if existing:
        return existing["id"]
    eid = str(uuid.uuid4())
    execute(
        "INSERT INTO entities (id, user_id, name, type) VALUES (%s, %s, %s, %s)",
        (eid, user_id, name, etype)
    )
    return eid


def _edge_exists(user_id: str, source_id: str, target_id: str, relationship: str) -> bool:
    """Check if a directed edge already exists to avoid duplicates."""
    row = execute_one(
        "SELECT id FROM edges WHERE user_id = %s AND source_id = %s AND target_id = %s AND relationship = %s",
        (user_id, source_id, target_id, relationship)
    )
    return row is not None


def _create_edge(user_id: str, source_id: str, source_type: str,
                 target_id: str, target_type: str, relationship: str, strength: float):
    """Insert edge only if it doesn't exist yet (idempotent)."""
    if _edge_exists(user_id, source_id, target_id, relationship):
        return
    execute(
        """INSERT INTO edges (id, user_id, source_id, source_type, target_id, target_type, relationship, strength)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (str(uuid.uuid4()), user_id, source_id, source_type, target_id, target_type, relationship, strength)
    )


def _link_by_term_overlap(user_id: str, doc_id: str, terms: list[str]):
    """Find other documents sharing any of the same terms and link them."""
    if not terms:
        return

    placeholders = ','.join(['%s'] * len(terms))
    params = [user_id, doc_id] + terms

    others = execute(
        f"""SELECT DISTINCT ed.source_id AS other_doc_id, COUNT(*) as shared_terms
            FROM edges ed
            JOIN entities e ON e.id = ed.target_id
            WHERE ed.user_id = %s
              AND ed.source_type = 'document'
              AND ed.source_id != %s
              AND LOWER(e.name) IN ({placeholders})
            GROUP BY ed.source_id
            HAVING COUNT(*) >= 1
            ORDER BY shared_terms DESC""",
        tuple(params)
    ) or []

    for row in others:
        o = dict(row)
        strength = min(0.95, 0.4 + (o["shared_terms"] * 0.12))
        # Single directed edge from this doc to the other;
        # Cytoscape treats undirected so we don't need the reverse
        _create_edge(user_id, doc_id, "document", o["other_doc_id"], "document",
                     "shares_concepts", round(strength, 3))

    if others:
        logger.info(f"KG: {doc_id[:8]} linked to {len(others)} docs via term overlap")


def _link_by_semantic_similarity(user_id: str, doc_id: str):
    """Use pgvector cosine similarity to link semantically similar documents."""
    doc_emb = execute_one(
        "SELECT embedding FROM documents WHERE id = %s AND embedding IS NOT NULL", (doc_id,)
    )
    if not doc_emb or not doc_emb.get("embedding"):
        return

    emb_val = doc_emb["embedding"]
    if isinstance(emb_val, str):
        emb_str = emb_val
    else:
        emb_str = json.dumps(list(emb_val))

    similar = execute(
        """SELECT d.id, d.title,
                  1 - (d.embedding <=> %s::vector) AS similarity
           FROM documents d
           WHERE d.user_id = %s AND d.id != %s AND d.embedding IS NOT NULL
             AND 1 - (d.embedding <=> %s::vector) > 0.60
           ORDER BY d.embedding <=> %s::vector
           LIMIT 8""",
        (emb_str, user_id, doc_id, emb_str, emb_str)
    ) or []

    for row in similar:
        s = dict(row)
        strength = min(0.92, float(s["similarity"]))
        _create_edge(user_id, doc_id, "document", s["id"], "document",
                     "semantically_similar", round(strength, 3))

    if similar:
        logger.info(f"KG: {doc_id[:8]} semantic links → {len(similar)} docs")


# ============================================================
# Graph Query API
# ============================================================

def get_user_graph(user_id: str, filter_category: str = None,
                   filter_entity_type: str = None, filter_keyword: str = None) -> dict:
    """Return nodes + edges for Cytoscape.js visualization."""
    docs = execute(
        "SELECT id, title, source_type, summary, word_count, category, keywords "
        "FROM documents WHERE user_id = %s",
        (user_id,)
    ) or []
    entities = execute(
        "SELECT id, name, type FROM entities WHERE user_id = %s", (user_id,)
    ) or []
    edges = execute(
        "SELECT source_id, source_type, target_id, target_type, relationship, strength "
        "FROM edges WHERE user_id = %s",
        (user_id,)
    ) or []

    doc_ids = {d["id"] for d in docs}
    entity_ids = {e["id"] for e in entities}

    # ── Build nodes ──
    nodes = []
    for d in docs:
        doc = dict(d)
        subtype = doc.get("source_type", "unknown")
        wc = doc.get("word_count") or 100
        size = min(50, max(24, wc // 120))
        nodes.append({
            "data": {
                "id":       doc["id"],
                "label":    doc["title"][:70],
                "type":     "document",
                "subtype":  subtype,
                "color":    DOC_TYPE_COLORS.get(subtype, "#6b7280"),
                "size":     size,
                "summary":  (doc.get("summary") or "")[:300],
                "category": doc.get("category") or "",
                "url":      f"/api/documents/{doc['id']}",
            }
        })

    for e in entities:
        ent = dict(e)
        etype = _normalize_type(ent.get("type", "topic"))
        nodes.append({
            "data": {
                "id":      ent["id"],
                "label":   ent["name"][:60],
                "type":    "entity",
                "subtype": etype,
                "color":   ENTITY_COLORS.get(etype, "#a1a1aa"),
                "size":    10,
                "summary": f"{etype}: {ent['name']}",
                "category": "",
                "url":     "",
            }
        })

    # ── Filtering ──
    keep_ids = doc_ids | entity_ids

    if filter_entity_type:
        norm = _normalize_type(filter_entity_type)
        keep_entity_ids = {e["id"] for e in entities if _normalize_type(e.get("type", "")) == norm}
        keep_ids = {nid for nid in keep_ids if nid in doc_ids or nid in keep_entity_ids}

    if filter_category:
        cat_doc_ids = {d["id"] for d in docs if d.get("category") == filter_category}
        connected = set()
        for ed in edges:
            if ed["source_id"] in cat_doc_ids and ed["target_id"] in entity_ids:
                connected.add(ed["target_id"])
            if ed["target_id"] in cat_doc_ids and ed["source_id"] in entity_ids:
                connected.add(ed["source_id"])
        keep_ids &= (cat_doc_ids | connected)

    if filter_keyword:
        kw = filter_keyword.lower()
        matching = set()
        for d in docs:
            kw_list = d.get("keywords") or []
            if (kw in d["title"].lower()
                    or kw in (d.get("summary") or "").lower()
                    or any(kw in k.lower() for k in kw_list)):
                matching.add(d["id"])
        for e in entities:
            if kw in e["name"].lower() or kw in e["type"].lower():
                matching.add(e["id"])
        # include first-degree neighbours
        neighbours = set()
        for ed in edges:
            if ed["source_id"] in matching:
                neighbours.add(ed["target_id"])
            if ed["target_id"] in matching:
                neighbours.add(ed["source_id"])
        keep_ids &= (matching | neighbours)

    nodes = [n for n in nodes if n["data"]["id"] in keep_ids]
    node_id_set = {n["data"]["id"] for n in nodes}

    # ── Build edges, deduplicate by canonical key ──
    seen_edges: set[str] = set()
    d3_edges = []
    for ed in edges:
        e = dict(ed)
        src, tgt, rel = e["source_id"], e["target_id"], e["relationship"]
        if src not in node_id_set or tgt not in node_id_set:
            continue
        # Canonical key: sort endpoints so a→b and b→a are the same visual edge
        canon = f"{min(src,tgt)}_{max(src,tgt)}_{rel}"
        if canon in seen_edges:
            continue
        seen_edges.add(canon)
        strength = float(e.get("strength") or 0.5)
        d3_edges.append({
            "data": {
                "id":           f"{src[:8]}_{tgt[:8]}_{rel}",
                "source":       src,
                "target":       tgt,
                "relationship": rel,
                "strength":     strength,
            }
        })

    return {"nodes": nodes, "edges": d3_edges}


def get_graph_stats(user_id: str) -> dict:
    doc_c  = execute_one("SELECT COUNT(*) as c FROM documents WHERE user_id = %s", (user_id,))
    ent_c  = execute_one("SELECT COUNT(*) as c FROM entities  WHERE user_id = %s", (user_id,))
    edge_c = execute_one("SELECT COUNT(*) as c FROM edges     WHERE user_id = %s", (user_id,))
    cross  = execute_one(
        """SELECT COUNT(*) as c FROM edges
           WHERE user_id = %s AND source_type = 'document' AND target_type = 'document'""",
        (user_id,)
    )
    return {
        "documents":           doc_c["c"]  if doc_c  else 0,
        "entities":            ent_c["c"]  if ent_c  else 0,
        "connections":         edge_c["c"] if edge_c else 0,
        "cross_document_links":cross["c"]  if cross  else 0,
    }


def rebuild_graph_for_user(user_id: str):
    """
    Hard-reset and rebuild the entire knowledge graph for a user using two passes:
    Pass 1 — Extract entities from every document and create doc→entity edges.
    Pass 2 — Create cross-document edges (term overlap + semantic similarity).
    This ensures all entity nodes exist before cross-linking begins.
    """
    logger.info(f"KG rebuild: clearing data for user {user_id[:8]}")
    execute("DELETE FROM edges    WHERE user_id = %s", (user_id,))
    execute("DELETE FROM entities WHERE user_id = %s", (user_id,))

    docs = execute("SELECT id FROM documents WHERE user_id = %s", (user_id,)) or []
    logger.info(f"KG rebuild: pass 1 — extracting entities for {len(docs)} documents")

    doc_terms: dict[str, list[str]] = {}

    for d in docs:
        doc_id = d["id"]
        try:
            doc = execute_one(
                "SELECT id, title, source_type, entities_json, keywords, category "
                "FROM documents WHERE id = %s",
                (doc_id,)
            )
            if not doc:
                continue
            doc = dict(doc)

            entities_data = doc.get("entities_json") or {}
            if isinstance(entities_data, str):
                try:
                    entities_data = json.loads(entities_data)
                except Exception:
                    entities_data = {}

            keywords = doc.get("keywords") or []
            if isinstance(keywords, str):
                try:
                    keywords = json.loads(keywords)
                except Exception:
                    keywords = []

            all_terms: list[str] = []

            for raw_etype, items in entities_data.items():
                if not isinstance(items, list):
                    continue
                etype = _normalize_type(raw_etype)
                for name in items[:10]:
                    name = str(name).strip()
                    if not name or len(name) < 2:
                        continue
                    name_lower = name.lower()
                    eid = _upsert_entity(user_id, name_lower, etype)
                    _create_edge(user_id, doc_id, "document", eid, "entity", f"has_{etype}", 0.9)
                    all_terms.append(name_lower)

            for kw in keywords[:10]:
                kw_str = str(kw).strip().lower()
                if not kw_str or len(kw_str) < 2:
                    continue
                eid = _upsert_entity(user_id, kw_str, "keyword")
                _create_edge(user_id, doc_id, "document", eid, "entity", "has_keyword", 0.85)
                all_terms.append(kw_str)

            category = doc.get("category")
            if category:
                cat = category.strip().lower()
                if cat:
                    eid = _upsert_entity(user_id, cat, "category")
                    _create_edge(user_id, doc_id, "document", eid, "entity", "in_category", 1.0)
                    all_terms.append(cat)

            title_clean = doc["title"].strip().lower()[:80]
            if title_clean:
                title_eid = _upsert_entity(user_id, title_clean, "topic")
                _create_edge(user_id, doc_id, "document", title_eid, "entity", "represents", 1.0)

            doc_terms[doc_id] = list(set(t for t in all_terms if t))
        except Exception as exc:
            logger.warning(f"KG rebuild pass1 failed for {doc_id[:8]}: {exc}")

    logger.info(f"KG rebuild: pass 2 — cross-linking {len(docs)} documents")
    for d in docs:
        doc_id = d["id"]
        try:
            _link_by_term_overlap(user_id, doc_id, doc_terms.get(doc_id, []))
        except Exception as exc:
            logger.warning(f"KG rebuild pass2 term-overlap failed for {doc_id[:8]}: {exc}")
        try:
            _link_by_semantic_similarity(user_id, doc_id)
        except Exception as exc:
            logger.warning(f"KG rebuild pass2 semantic failed for {doc_id[:8]}: {exc}")

    logger.info(f"KG rebuild: complete — {len(docs)} docs processed")


# Back-compat alias (used by old process_all_existing calls)
def process_all_existing(user_id: str):
    rebuild_graph_for_user(user_id)
