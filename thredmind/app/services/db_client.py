import psycopg2
import psycopg2.extras
from app.config import settings

_connection = None


def get_connection():
    global _connection
    if _connection is None or _connection.closed:
        _connection = psycopg2.connect(settings.DATABASE_URL)
        _connection.autocommit = True
    return _connection


def _reset_connection():
    """Close and discard the current connection so the next call reconnects."""
    global _connection
    try:
        if _connection and not _connection.closed:
            _connection.close()
    except Exception:
        pass
    _connection = None


def execute(sql, params=None, fetch=True):
    for attempt in range(2):
        try:
            conn = get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                if fetch and cur.description:
                    return cur.fetchall()
            return None
        except psycopg2.OperationalError:
            if attempt == 0:
                _reset_connection()
            else:
                raise


def execute_one(sql, params=None):
    for attempt in range(2):
        try:
            conn = get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                if cur.description:
                    return cur.fetchone()
            return None
        except psycopg2.OperationalError:
            if attempt == 0:
                _reset_connection()
            else:
                raise


def init_db():
    execute("""
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS documents (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_url TEXT,
            content_text TEXT,
            summary TEXT,
            entities_json JSONB DEFAULT '{}',
            keywords TEXT[] DEFAULT '{}',
            embedding vector(384),
            word_count INTEGER DEFAULT 0,
            category VARCHAR(100),
            is_favorite BOOLEAN DEFAULT FALSE,
            parent_document_id UUID REFERENCES documents(id),
            study_slides_json JSONB,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        );

        ALTER TABLE documents ADD COLUMN IF NOT EXISTS category VARCHAR(100);
        ALTER TABLE documents ADD COLUMN IF NOT EXISTS is_favorite BOOLEAN DEFAULT FALSE;
        ALTER TABLE documents ADD COLUMN IF NOT EXISTS parent_document_id UUID;
        ALTER TABLE documents ADD COLUMN IF NOT EXISTS study_slides_json JSONB;

        CREATE TABLE IF NOT EXISTS categories (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            color VARCHAR(7) DEFAULT '#60a5fa',
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(user_id, name)
        );

        CREATE TABLE IF NOT EXISTS entities (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(user_id, name, type)
        );

        CREATE TABLE IF NOT EXISTS edges (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_id UUID NOT NULL,
            source_type TEXT NOT NULL,
            target_id UUID NOT NULL,
            target_type TEXT NOT NULL,
            relationship TEXT DEFAULT 'related_to',
            strength FLOAT DEFAULT 0.0,
            created_at TIMESTAMPTZ DEFAULT now()
        );

        -- Indexes for fast graph lookups
        CREATE INDEX IF NOT EXISTS idx_edges_user_source  ON edges (user_id, source_id);
        CREATE INDEX IF NOT EXISTS idx_edges_user_target  ON edges (user_id, target_id);
        CREATE INDEX IF NOT EXISTS idx_entities_user_name ON entities (user_id, name, type);

        CREATE TABLE IF NOT EXISTS chat_sessions (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT DEFAULT 'New Chat',
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            citations_json JSONB,
            created_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS study_progress (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            study_count INTEGER DEFAULT 1,
            last_studied TIMESTAMPTZ DEFAULT now(),
            next_review TIMESTAMPTZ,
            review_interval INTEGER DEFAULT 1,
            mastery VARCHAR(20) DEFAULT 'learning',
            completed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(user_id, document_id)
        );

        CREATE TABLE IF NOT EXISTS user_study_stats (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            current_streak INTEGER DEFAULT 0,
            longest_streak INTEGER DEFAULT 0,
            last_study_date DATE,
            total_sessions INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        );
    """)
