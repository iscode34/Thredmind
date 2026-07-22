"""
Local embedding service using fastembed + ONNX Runtime.
Uses BAAI/bge-small-en-v1.5 (384-dim) — runs entirely on-device with GPU auto-detection.
No API calls, no costs, no latency.
"""
import json
import logging
from fastembed import TextEmbedding
from app.services.db_client import execute

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
_MODEL = None


def _get_model() -> TextEmbedding:
    """Lazy-load the embedding model (downloaded on first use, cached thereafter)."""
    global _MODEL
    if _MODEL is None:
        logger.info("Loading local embedding model (BAAI/bge-small-en-v1.5)...")
        _MODEL = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        logger.info("Embedding model ready (384-dim, ONNX Runtime)")
    return _MODEL


def generate_embedding(text: str) -> list[float]:
    """Generate a 384-dimensional embedding vector for the given text."""
    if not text or not text.strip():
        raise ValueError("Empty text for embedding")

    model = _get_model()
    # bge models prefer passage-like input; truncate for performance
    truncated = text[:2000]
    embeddings = list(model.embed([truncated]))
    return embeddings[0].tolist()


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts in a single batch (much faster)."""
    if not texts:
        return []
    model = _get_model()
    truncated = [t[:2000] for t in texts]
    embeddings = list(model.embed(truncated))
    return [e.tolist() for e in embeddings]


def store_embedding(document_id: str, embedding: list[float]):
    """Store an embedding vector in the documents table."""
    execute(
        "UPDATE documents SET embedding = %s::vector WHERE id = %s",
        (json.dumps(embedding), document_id),
    )


def search_similar(query: str, user_id: str = None, limit: int = 5) -> list[dict]:
    """Semantic search: find documents most similar to the query using pgvector cosine distance."""
    query_embedding = generate_embedding(query)
    embedding_str = json.dumps(query_embedding)

    rows = execute(
        """SELECT d.id, d.title, d.summary, d.source_type, d.word_count,
                  1 - (d.embedding <=> %s::vector) AS similarity
           FROM documents d
           WHERE d.embedding IS NOT NULL
           ORDER BY d.embedding <=> %s::vector
           LIMIT %s""",
        (embedding_str, embedding_str, limit),
    ) or []

    results = []
    for row in rows:
        r = dict(row)
        r["similarity"] = round(float(r["similarity"]) * 100, 1)
        results.append(r)
    return results


def search_chunks(query: str, user_id: str = None, limit: int = 5) -> list[dict]:
    """Chunk-based semantic search for RAG — returns documents with snippets."""
    query_embedding = generate_embedding(query)
    embedding_str = json.dumps(query_embedding)

    rows = execute(
        """SELECT d.id, d.title, d.summary, d.content_text, d.source_type,
                  1 - (d.embedding <=> %s::vector) AS similarity
           FROM documents d
           WHERE d.embedding IS NOT NULL
           ORDER BY d.embedding <=> %s::vector
           LIMIT %s""",
        (embedding_str, embedding_str, limit),
    ) or []

    results = []
    for row in rows:
        r = dict(row)
        r["similarity"] = round(float(r["similarity"]) * 100, 1)
        # Extract a relevant snippet (first 300 chars of content or summary)
        text = r.get("content_text") or ""
        r["snippet"] = text[:500] if text else (r.get("summary") or "")[:500]
        # Remove full content_text from response (too large)
        r.pop("content_text", None)
        results.append(r)
    return results
