# ThredMind — AI Personal Knowledge Workspace

## Project Plan & Technical Blueprint

---

## 1. PROJECT OVERVIEW

**ThredMind** is a web platform that turns scattered information into an interconnected, searchable knowledge base. Users upload documents, paste URLs, or import content from multiple sources. AI processes everything, builds relationships between concepts, and gives users a searchable, graph-connected knowledge library.

**One-liner:** "Notion + Obsidian + ChatGPT" — but everything is auto-connected by AI.

**Target Users:** Students, researchers, professionals, content creators, lifelong learners.

**Core Philosophy:** Process → Analyze → Store (metadata only, no permanent file storage). Privacy-first, free-tier-friendly.

---

## 2. TECH STACK (All Free / Generous Free Tier)

| Layer | Technology | Why | Free Tier |
|---|---|---|---|
| **Backend** | FastAPI (Python 3.11+) | Async, fast, auto-docs, modern Python | 100% free |
| **Database** | Neon (Serverless PostgreSQL) | Serverless Postgres with pgvector, scales to zero | 0.5GB storage, 1 project free |
| **Vector DB** | pgvector (Neon extension) | Same DB, no extra infra | Included in Neon |
| **Auth** | FastAPI + JWT (python-jose) + bcrypt | Self-contained auth, no third-party dependency | 100% free |
| **AI / LLM** | DeepSeek API / OpenAI API (GPT-4o-mini) | DeepSeek: cheap + powerful; OpenAI: best quality for cheap | Pay-per-use |
| **AI Backup** | Groq (LLaMA 3) | Free tier for basic tasks | Free tier available |
| **Task Queue** | Python asyncio + BackgroundTasks | Simple, no Redis needed for MVP | 100% free |
| **Frontend** | FastAPI + Jinja2 + Tailwind CSS + HTMX | Pure Python, vibecoding-friendly, no JS framework needed | 100% free |
| **File Processing** | PyPDF2, python-docx, python-pptx, BeautifulSoup, youtube-transcript-api | Parse any format | 100% free |
| **Deployment** | Render (web service) | Simple, free SSL, auto-deploy | 750hrs/month free |

### Cost Estimate for MVP
- DeepSeek / OpenAI API: ~$3-10/month (during development/testing)
- Neon Database: **$0/month** (free tier)
- Everything else: **$0/month**
- Total: **$3-10/month**

---

## 3. CORE FEATURES (MVP — 5 Features)

| # | Feature | Complexity | Priority |
|---|---|---|---|
| 1 | **Document Upload & Processing** | ⭐⭐ | P0 |
| 2 | **Website URL Import** | ⭐⭐⭐ | P0 |
| 3 | **AI Processing Pipeline** (summary, entities, keywords) | ⭐⭐⭐⭐ | P0 |
| 4 | **Chat with Knowledge** (RAG — ask questions about your content) | ⭐⭐⭐⭐ | P0 |
| 5 | **Knowledge Graph Explorer** (visual node graph) | ⭐⭐⭐⭐⭐ | P0 — X-Factor |

---

## 4. FEATURE DETAILS

### Feature 1: Document Upload & Processing

**What it does:**
User uploads a file (PDF, DOCX, TXT, MD, PPTX). The system extracts text, processes it with AI, and stores the extracted content + metadata in the database. The original file is NOT stored permanently — processed in memory and discarded.

**Supported formats:**
- PDF (PyPDF2)
- Word / DOCX (python-docx)
- PowerPoint / PPTX (python-pptx)
- Plain text / TXT
- Markdown / MD

**Flow:**
```
User uploads file → File read into memory → Text extracted → 
AI processes (summary, entities, keywords) → Data saved to DB → 
File deleted from memory → Result shown to user
```

**Output per document:**
- Extracted full text
- AI-generated summary (200-300 words)
- Key entities extracted (people, topics, concepts, dates)
- Keywords / tags
- Word count, reading time

---

### Feature 2: Website URL Import

**What it does:**
User pastes any URL. The system fetches the page, extracts the main content (stripping nav, ads, sidebars), and processes it exactly like a document.

**Flow:**
```
User pastes URL → Server fetches page HTML → 
Readability algorithm extracts main content → 
Text cleaned → AI processes → Data saved → Done
```

**Edge cases handled:**
- Paywalled pages (fetch what's available)
- JavaScript-heavy sites (fallback to basic HTML parsing)
- Invalid URLs (graceful error message)

---

### Feature 3: AI Processing Pipeline

**What it does:**
This is the brain. Every piece of content that enters the system goes through a 3-step AI pipeline:

**Step 1 — Summarization:**
Generates a concise, accurate summary of the content (200-300 words).

**Step 2 — Entity & Concept Extraction:**
Identifies key entities:
- People mentioned
- Topics / concepts
- Dates / timelines
- Organizations
- Technical terms

**Step 3 — Keyword & Tag Generation:**
Generates 5-10 relevant keywords/tags for searchability.

**Prompt Design (single call for efficiency):**
All 3 steps are done in ONE OpenAI API call using a structured prompt, reducing cost and latency. The response is parsed as JSON.

**Output schema:**
```json
{
  "summary": "...",
  "entities": {
    "people": ["..."],
    "topics": ["..."],
    "organizations": ["..."],
    "dates": ["..."]
  },
  "keywords": ["..."]
}
```

---

### Feature 4: Chat with Knowledge (RAG)

**What it does:**
A ChatGPT-style interface where the AI answers questions based ONLY on the user's uploaded knowledge. It cites which documents it used to answer.

**How RAG (Retrieval-Augmented Generation) works:**
```
User asks question → 
Question is embedded into vector → 
pgvector finds top 5 most relevant document chunks → 
Chunks + question sent to OpenAI as context → 
AI answers with citations → 
Response shown to user
```

**Example:**
> **User asks:** "What are the key differences between CNNs and Transformers?"
>
> **AI responds:** "Based on your uploaded documents:
> 1. CNNs excel at spatial data (images) — from your 'Deep Learning Basics' PDF (page 3)
> 2. Transformers handle sequential data better and use self-attention — from your 'Attention Is All You Need' paper
> 3. CNNs have fewer parameters for similar tasks — from your 'Model Comparison' notes"

**Chat features:**
- Conversational memory (remembers previous messages in the session)
- Clickable citations that open the source document
- "I don't know" response when no relevant docs found (no hallucination)

---

### Feature 5: Knowledge Graph Explorer

**What it does:**
A visual, interactive graph showing how all uploaded documents and concepts are connected. This is the **X-Factor** — the visual "wow" moment.

**Graph structure:**
- **Nodes:** Documents, Concepts, People, Topics
- **Edges (connections):** "mentions", "related to", "cites", "part of"

**How connections are built:**
When a new document is added:
1. Its entities are compared against all existing entities in the database
2. If entities overlap (same concept, same person, same topic), an edge is created
3. Edges have a "strength" based on how many entities they share

**Visual experience:**
- Force-directed graph layout (using D3.js or vis.js)
- Drag nodes, zoom in/out
- Click a node to see connected documents
- Color-coded by type (blue=document, green=concept, orange=person)
- Hover to see relationship preview

**Why it's the X-Factor:**
- It visualizes knowledge connections users never knew existed
- Highly screenshot-worthy (users share on social media)
- Makes the platform feel like a "second brain"

---

## 5. DATABASE SCHEMA (Neon / PostgreSQL)

### Table: `users`
Stores user accounts (managed by FastAPI JWT auth).

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Unique user ID |
| `email` | TEXT (UNIQUE) | User email |
| `password_hash` | TEXT | bcrypt hashed password |
| `created_at` | TIMESTAMPTZ | Signup time |

### Table: `documents`
Stores processed document metadata and content.

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Unique document ID |
| `user_id` | UUID (FK → users) | Owner |
| `title` | TEXT | Document title (from filename or URL) |
| `source_type` | TEXT | 'pdf', 'docx', 'pptx', 'txt', 'md', 'url' |
| `source_url` | TEXT (nullable) | Original URL if web import |
| `content_text` | TEXT | Full extracted text |
| `summary` | TEXT | AI-generated summary |
| `entities_json` | JSONB | Extracted entities (people, topics, etc.) |
| `keywords` | TEXT[] | Array of tags/keywords |
| `embedding` | VECTOR(1536) | For semantic search (pgvector) |
| `word_count` | INTEGER | Word count |
| `created_at` | TIMESTAMPTZ | Upload time |
| `updated_at` | TIMESTAMPTZ | Last modified |

### Table: `entities`
Stores unique entities across all documents.

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Unique entity ID |
| `user_id` | UUID (FK) | Owner |
| `name` | TEXT | Entity name |
| `type` | TEXT | 'person', 'topic', 'organization', 'concept' |
| `created_at` | TIMESTAMPTZ | Creation time |

### Table: `edges`
Stores connections between documents and entities (for Knowledge Graph).

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Unique edge ID |
| `user_id` | UUID (FK) | Owner |
| `source_id` | UUID | Source node (document or entity ID) |
| `source_type` | TEXT | 'document' or 'entity' |
| `target_id` | UUID | Target node ID |
| `target_type` | TEXT | 'document' or 'entity' |
| `relationship` | TEXT | 'mentions', 'related_to', 'cites', 'shares_concept' |
| `strength` | FLOAT | 0.0–1.0, based on entity overlap |
| `created_at` | TIMESTAMPTZ | Creation time |

### Table: `chat_sessions`
Stores chat history.

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Session ID |
| `user_id` | UUID (FK) | Owner |
| `title` | TEXT | Auto-generated session title |
| `created_at` | TIMESTAMPTZ | Start time |
| `updated_at` | TIMESTAMPTZ | Last message time |

### Table: `chat_messages`
Individual messages within a chat session.

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Message ID |
| `session_id` | UUID (FK → chat_sessions) | Parent session |
| `role` | TEXT | 'user' or 'assistant' |
| `content` | TEXT | Message text |
| `citations_json` | JSONB (nullable) | Source document references |
| `created_at` | TIMESTAMPTZ | Message time |

---

## 6. API ENDPOINTS

### Auth (Handled by FastAPI JWT Auth)
```
POST   /auth/signup
POST   /auth/login
POST   /auth/logout
GET    /auth/me
```

### Documents
```
POST   /api/documents/upload      — Upload & process file
POST   /api/documents/import-url  — Import from URL
GET    /api/documents              — List all user's documents
GET    /api/documents/{id}         — Get single document details
DELETE /api/documents/{id}         — Delete document
```

### Chat
```
POST   /api/chat/sessions          — Create new chat session
GET    /api/chat/sessions          — List user's sessions
GET    /api/chat/sessions/{id}     — Get session messages
POST   /api/chat/sessions/{id}/messages  — Send message, get AI response
DELETE /api/chat/sessions/{id}     — Delete session
```

### Knowledge Graph
```
GET    /api/graph/data             — Get full graph data (nodes + edges)
GET    /api/graph/node/{id}        — Get node details + connections
```

### Dashboard
```
GET    /api/dashboard/stats        — Document count, entity count, recent activity
```

---

## 7. PROJECT STRUCTURE

```
thredmind/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Environment variables, settings
│   ├── dependencies.py          # Dependency injection (DB sessions, auth)
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py              # Auth routes (JWT-based)
│   │   ├── documents.py         # Document upload/import routes
│   │   ├── chat.py              # Chat/RAG routes
│   │   ├── graph.py             # Knowledge Graph routes
│   │   └── dashboard.py         # Dashboard/stats routes
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── document_parser.py   # Extract text from PDF, DOCX, PPTX, TXT
│   │   ├── web_scraper.py       # Fetch & extract content from URLs
│   │   ├── ai_processor.py      # DeepSeek/OpenAI calls (summary, entities, keywords)
│   │   ├── embedding_service.py # Generate & store vector embeddings
│   │   ├── chat_service.py      # RAG chat logic
│   │   ├── graph_service.py     # Build & query knowledge graph
│   │   └── db_client.py         # Neon DB client
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── document.py          # Pydantic models for documents
│   │   ├── chat.py              # Pydantic models for chat
│   │   ├── graph.py             # Pydantic models for graph
│   │   └── user.py              # Pydantic models for auth
│   │
│   └── templates/               # Jinja2 HTML templates
│       ├── base.html            # Base layout (navbar, footer)
│       ├── index.html           # Landing / dashboard
│       ├── login.html           # Login page
│       ├── signup.html          # Signup page
│       ├── upload.html          # Document upload page
│       ├── documents.html       # Document list
│       ├── document_detail.html # Single document view
│       ├── chat.html            # Chat interface
│       ├── graph.html           # Knowledge Graph explorer
│       └── dashboard.html       # Stats dashboard
│
├── static/
│   ├── css/
│   │   └── tailwind.css         # Tailwind CSS (compiled)
│   ├── js/
│   │   ├── graph.js             # Knowledge Graph visualization (D3.js/vis.js)
│   │   ├── chat.js              # Chat interface logic
│   │   └── upload.js            # Upload progress & preview
│   └── img/
│
├── tests/
│   ├── test_documents.py
│   ├── test_search.py
│   └── test_chat.py
│
├── .env                         # Environment variables (secrets)
├── .env.example                 # Template for .env
├── .gitignore
├── requirements.txt             # Python dependencies
├── schema.sql                   # Database schema (for reference)
└── plan.md                      # This file
```

---

## 8. X-FACTOR FEATURES (What Makes It Viral)

### X1: Knowledge Graph Visualizer
Already covered in Feature 5. The visual, draggable graph is screenshot-bait.

### X2: Blind Spot Detector
The AI proactively tells users what they DON'T know.
- Analyzes knowledge graph for missing connections
- Says: "You understand A and B, but C connects them. You have no content on C. Here's what to learn."
- Makes users feel like the platform is looking out for them.

### X3: Timeline View
Shows when each piece of knowledge was added, organized chronologically.
- "Your journey from Python basics → Machine Learning → Deep Learning across 3 months."
- Great for reflecting on learning progress.

### X4: Auto-Quiz Generator
One-click generate 5 quiz questions from any document.
- Multiple choice + short answer
- Tests actual understanding
- Powerful for students

### X5: "Connection Surprise"
When uploading new content, the AI says:
> "Your new document on 'Transformers' shares 7 concepts with your 3-month-old lecture notes on 'Attention Mechanisms.' Here's what they have in common..."
This moment of unexpected connection is what makes users stay.

---

## 9. BUILD PHASES

### Phase 1: Foundation (Week 1)
- Set up FastAPI project structure
- Set up Neon database project (DB + pgvector)
- Create database tables + enable pgvector
- Implement user signup/login (FastAPI JWT + bcrypt)
- Basic HTML templates with Tailwind CSS
- Deploy to Render (verify everything works)

**Deliverable:** Working app with auth, empty dashboard.

### Phase 2: Document Processing (Week 1-2)
- Build document upload endpoint (PDF, DOCX, TXT)
- Build URL import endpoint (fetch + extract content)
- Build AI processing pipeline (DeepSeek/OpenAI: summary + entities + keywords)
- Create document list + detail views
- Generate and store embeddings in pgvector

**Deliverable:** Users can upload docs/URLs and see AI-processed results.

### Phase 3: Chat with Knowledge (Week 2-3)
- Implement RAG pipeline (embed question → find relevant chunks → generate answer)
- Build chat UI (message list, input, citations)
- Implement chat sessions (create, list, delete)
- Add citation links (click → open source document)

**Deliverable:** Users can chat with their knowledge base.

### Phase 4: Knowledge Graph (Week 3)
- Build graph data API (nodes + edges from entities)
- Implement edge creation logic (entity overlap detection)
- Build interactive graph visualization (D3.js force-directed graph)
- Add node click → document detail navigation

**Deliverable:** Visual knowledge graph explorer.

### Phase 5: Polish & X-Factor (Week 3-4)
- Add dashboard with stats
- Add Blind Spot Detector
- Add Auto-Quiz Generator
- UI polish, error handling, loading states
- Write tests

**Deliverable:** Complete, polished MVP.

---

## 10. STEP-BY-STEP BUILD ORDER (Exact Commands)

### Step 1: Project Scaffold
```bash
mkdir knowledge-os && cd knowledge-os
python -m venv venv
venv\Scripts\activate
pip install fastapi uvicorn jinja2 python-multipart openai \
    PyPDF2 python-docx python-pptx beautifulsoup4 lxml \
    readability-lxml newspaper3k youtube-transcript-api \
    python-dotenv httpx pytest bcrypt python-jose[cryptography] \
    psycopg2-binary
pip freeze > requirements.txt
```

### Step 2: Create FastAPI App (`app/main.py`)
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.routes import auth, documents, chat, graph, dashboard

app = FastAPI(title="ThredMind", version="0.1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(graph.router, prefix="/api/graph", tags=["Graph"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
```

### Step 3: Set Up Neon Database
1. Create free account at [neon.tech](https://neon.tech)
2. Create new project → get `DATABASE_URL` (connection string)
3. Enable `pgvector` extension (SQL Editor → `CREATE EXTENSION vector;`)
4. Run `schema.sql` to create tables

### Step 4: Environment Variables (`.env`)
```
DATABASE_URL=postgresql://user:pass@ep-xxxx.us-east-2.aws.neon.tech/dbname?sslmode=require
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=sk-...
JWT_SECRET_KEY=your-secret-key
```

### Step 5: Build Features in Order
Follow Phase 1 → Phase 5 from Section 9. Each phase ends with a working, testable feature.

---

## 11. KEY DESIGN DECISIONS

### Why No Permanent File Storage?
- Saves costs (no S3/R2 needed)
- Privacy-first (nothing stored = nothing leaked)
- Simpler architecture
- Focus on extracted knowledge, not raw files
- If users need files later, they'll re-upload

### Why Single AI Call for Processing?
- Cost optimization (3 tasks in 1 API call)
- Faster processing
- Simple prompt design with structured JSON output
- Use DeepSeek API as primary (cheaper), OpenAI as fallback

### Why pgvector Instead of Pinecone/Weaviate?
- Zero extra cost (extends existing Neon PostgreSQL)
- No separate service to manage
- Good enough for MVP scale (<100k documents)
- Can migrate to Pinecone later if needed

### Why Jinja2 + HTMX Instead of React?
- Pure Python stack (easier for university project)
- Lower complexity
- Faster to build
- HTMX gives SPA-like feel without JS framework
- Can add React later if needed

### Why JWT + bcrypt Instead of Neon Auth?
- Neon Auth is in Beta and built for JS frameworks (Next.js, React)
- FastAPI stack needs a Python-native solution — no JS SDK dependency
- bcrypt + JWT with HTTPS is production-grade secure
- Self-contained: no external auth service to manage
- Can migrate to Neon Auth post-MVP if needed (60k MAU free tier)

---

## 12. FUTURE EXPANSION IDEAS (Post-MVP)

- **Semantic Search** — Search by meaning across all documents (pgvector cosine similarity + autocomplete)
- YouTube video import (youtube-transcript-api)
- Audio upload with speech-to-text (OpenAI Whisper)
- OCR for images (Tesseract)
- Team/org collaboration
- Browser extension (one-click save)
- Mobile PWA
- Export as PDF/Notion/Markdown
- Public knowledge sharing (like a blog)
- Integration with Google Drive, Notion, Slack
- Flashcard export to Anki
- AI-generated mind maps
- Learning streak & gamification

---

## 13. SUCCESS METRICS FOR UNI PROJECT

| Metric | Target |
|---|---|
| Upload processing time | <10 seconds per document |
| Chat response time | <5 seconds |
| Graph rendering | <3 seconds for 100+ nodes |
| Uptime | Stable on Render free tier |
| Code quality | Clean, documented, testable |
| Demo-ability | Can showcase all 5 MVP features live |

---

*End of Plan — Ready to Build*
