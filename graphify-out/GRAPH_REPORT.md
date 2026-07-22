# Graph Report - thredmind  (2026-07-10)

## Corpus Check
- 21 files · ~20,564 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 195 nodes · 293 edges · 21 communities (20 shown, 1 thin omitted)
- Extraction: 75% EXTRACTED · 25% INFERRED · 0% AMBIGUOUS · INFERRED: 73 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Document Management|Document Management]]
- [[_COMMUNITY_AIRAG Architecture|AI/RAG Architecture]]
- [[_COMMUNITY_Authentication System|Authentication System]]
- [[_COMMUNITY_Frontend Templates|Frontend Templates]]
- [[_COMMUNITY_Data Models|Data Models]]
- [[_COMMUNITY_App Routing|App Routing]]
- [[_COMMUNITY_Document Parsing|Document Parsing]]
- [[_COMMUNITY_AI Processing|AI Processing]]
- [[_COMMUNITY_Configuration|Configuration]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]

## God Nodes (most connected - your core abstractions)
1. `execute()` - 25 edges
2. `get_current_user()` - 22 edges
3. `execute_one()` - 20 edges
4. `ThredMind — AI Personal Knowledge Workspace` - 15 edges
5. `ThredMind` - 14 edges
6. `theme_from_request()` - 9 edges
7. `_process_and_respond()` - 9 edges
8. `Base Template` - 9 edges
9. `5. DATABASE SCHEMA (Neon / PostgreSQL)` - 7 edges
10. `dashboard()` - 6 edges

## Surprising Connections (you probably didn't know these)
- `import_url()` --calls--> `fetch_and_extract()`  [INFERRED]
  thredmind/app/routes/documents.py → E:/Nusa Putra/Python Project/thredmind/app/services/web_scraper.py
- `login_page()` --calls--> `get_current_user()`  [INFERRED]
  thredmind/app/routes/auth.py → E:/Nusa Putra/Python Project/thredmind/app/dependencies.py
- `signup_page()` --calls--> `get_current_user()`  [INFERRED]
  thredmind/app/routes/auth.py → E:/Nusa Putra/Python Project/thredmind/app/dependencies.py
- `dashboard()` --calls--> `get_current_user()`  [INFERRED]
  thredmind/app/routes/dashboard.py → E:/Nusa Putra/Python Project/thredmind/app/dependencies.py
- `study_library()` --calls--> `theme_from_request()`  [INFERRED]
  thredmind/app/main.py → E:/Nusa Putra/Python Project/thredmind/app/dependencies.py

## Hyperedges (group relationships)
- **Document Processing Flow** — plan_document_upload, plan_ai_processing_pipeline, plan_rag, plan_pgvector [EXTRACTED 1.00]
- **Frontend Template Stack** — templates_base, templates_sidebar, templates_theme_system, templates_htmx [EXTRACTED 1.00]
- **Authentication Stack** — plan_jwt_auth, plan_jwt_vs_neon_auth, plan_fastapi [EXTRACTED 1.00]

## Communities (21 total, 1 thin omitted)

### Community 0 - "Document Management"
Cohesion: 0.15
Nodes (34): get_current_user(), study_library(), ai_continue_study(), _build_study_response(), _build_study_slides_html(), create_category(), delete_category(), delete_document() (+26 more)

### Community 1 - "AI/RAG Architecture"
Cohesion: 0.13
Nodes (20): AI Processing Pipeline, Blind Spot Detector, Document Upload and Processing, FastAPI Backend, Jinja2 + HTMX Frontend Stack, Jinja2+HTMX Over React, JWT Authentication, JWT+brypt Over Neon Auth (+12 more)

### Community 2 - "Authentication System"
Cohesion: 0.22
Nodes (9): create_access_token(), require_auth(), theme_from_request(), login(), login_page(), logout(), signup(), signup_page() (+1 more)

### Community 3 - "Frontend Templates"
Cohesion: 0.15
Nodes (13): Auto-Quiz Generator, Base Template, Document Detail Page, Documents List Page, HTMX Partial Updates, Dashboard/Index Page, Mermaid Diagram Rendering, Quiz Generation Feature (+5 more)

### Community 4 - "Data Models"
Cohesion: 0.36
Nodes (6): BaseModel, DocumentListResponse, DocumentResponse, LoginRequest, SignupRequest, UserResponse

### Community 5 - "App Routing"
Cohesion: 0.21
Nodes (8): lifespan(), Redirect /study to documents page where users can select documents to study, root(), study_redirect(), get_connection(), init_db(), Close and discard the current connection so the next call reconnects., _reset_connection()

### Community 6 - "Document Parsing"
Cohesion: 0.7
Nodes (4): _extract_docx(), _extract_pdf(), _extract_pptx(), extract_text_from_file()

### Community 7 - "AI Processing"
Cohesion: 0.38
Nodes (3): chat_completion(), _parse_ai_response(), process_content()

### Community 8 - "Configuration"
Cohesion: 0.6
Nodes (3): database_url(), jwt_secret(), Settings

### Community 15 - "Community 15"
Cohesion: 0.07
Nodes (29): 11. KEY DESIGN DECISIONS, 12. FUTURE EXPANSION IDEAS (Post-MVP), 13. SUCCESS METRICS FOR UNI PROJECT, 1. PROJECT OVERVIEW, 2. TECH STACK (All Free / Generous Free Tier), 3. CORE FEATURES (MVP — 5 Features), 5. DATABASE SCHEMA (Neon / PostgreSQL), 7. PROJECT STRUCTURE (+21 more)

### Community 16 - "Community 16"
Cohesion: 0.18
Nodes (11): 6. API ENDPOINTS, Auth (Handled by FastAPI JWT Auth), Chat, code:block5 (POST   /auth/signup), code:block6 (POST   /api/documents/upload      — Upload & process file), code:block7 (POST   /api/chat/sessions          — Create new chat session), code:block8 (GET    /api/graph/data             — Get full graph data (no), code:block9 (GET    /api/dashboard/stats        — Document count, entity ) (+3 more)

### Community 17 - "Community 17"
Cohesion: 0.2
Nodes (10): 4. FEATURE DETAILS, code:block1 (User uploads file → File read into memory → Text extracted →), code:block2 (User pastes URL → Server fetches page HTML →), code:json ({), code:block4 (User asks question →), Feature 1: Document Upload & Processing, Feature 2: Website URL Import, Feature 3: AI Processing Pipeline (+2 more)

### Community 18 - "Community 18"
Cohesion: 0.22
Nodes (9): 10. STEP-BY-STEP BUILD ORDER (Exact Commands), code:bash (mkdir knowledge-os && cd knowledge-os), code:python (from fastapi import FastAPI), code:block13 (DATABASE_URL=postgresql://user:pass@ep-xxxx.us-east-2.aws.ne), Step 1: Project Scaffold, Step 2: Create FastAPI App (`app/main.py`), Step 3: Set Up Neon Database, Step 4: Environment Variables (`.env`) (+1 more)

### Community 19 - "Community 19"
Cohesion: 0.33
Nodes (6): 9. BUILD PHASES, Phase 1: Foundation (Week 1), Phase 2: Document Processing (Week 1-2), Phase 3: Chat with Knowledge (Week 2-3), Phase 4: Knowledge Graph (Week 3), Phase 5: Polish & X-Factor (Week 3-4)

## Knowledge Gaps
- **71 isolated node(s):** `Return the URL of the next unstudied document, or the first document.`, `Build HTML for study slides from sections list.`, `Build the full study HTML response with navigation, script, and completion modal`, `Record a study session for spaced repetition tracking.`, `Mark a study session as completed.` (+66 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ThredMind — AI Personal Knowledge Workspace` connect `Community 15` to `Community 16`, `Community 17`, `Community 18`, `Community 19`?**
  _High betweenness centrality (0.100) - this node is a cross-community bridge._
- **Why does `execute()` connect `Document Management` to `Authentication System`, `App Routing`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Why does `_process_and_respond()` connect `Document Management` to `AI Processing`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Are the 19 inferred relationships involving `execute()` (e.g. with `study_library()` and `signup()`) actually correct?**
  _`execute()` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `get_current_user()` (e.g. with `execute_one()` and `study_library()`) actually correct?**
  _`get_current_user()` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `execute_one()` (e.g. with `get_current_user()` and `study_library()`) actually correct?**
  _`execute_one()` has 15 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Return the URL of the next unstudied document, or the first document.`, `Build HTML for study slides from sections list.`, `Build the full study HTML response with navigation, script, and completion modal` to the rest of the system?**
  _71 weakly-connected nodes found - possible documentation gaps or missing edges._