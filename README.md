# Resume Tailoring Assistant

An LLM-powered resume tailoring system built with FastAPI, LangGraph, and Vue 3. The system parses your existing resume from PDF, analyzes job descriptions, and generates a tailored resume draft through a multi-agent pipeline. An interactive chat assistant allows you to refine the result.

## Features

- **PDF Resume Import** — Upload your resume PDF; a two-phase LLM pipeline extracts and structures your work experience, education, projects, and skills
- **JD Analysis & Matching** — Paste a job description to get a semantic skill match report with highlighted relevant experiences
- **AI Resume Generation** — Single-pass LLM tailoring that preserves your actual experience while optimizing keyword coverage
- **Keyword Scoring** — Rule-based coverage metrics for hard requirements, core keywords, preferred qualifications, and soft skills
- **Copilot Diagnostic Panel** — Three-tier resume audit: rule-based field checks, LLM macro analysis, and micro-level bullet improvements
- **Chat Assistant** — Intent-aware streaming chat that routes to local patch, keyword injection, full diagnosis, or Q&A based on your message
- **Session Management** — All analysis and draft sessions are persisted and resumable

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy (async), PostgreSQL |
| LLM Orchestration | LangGraph, LangChain Core |
| LLM Provider | Google Gemini (Flash / Flash Lite via `langchain-google-genai`) |
| PDF Parsing | PyMuPDF |
| Frontend | Vue 3, Vite, Naive UI, TypeScript |
| Auth | JWT (python-jose), bcrypt (pwdlib) |
| PDF Export | Playwright (headless Chromium) |

## Project Structure

```
app/
  agents/           # LLM agents (one class per agent, stateless)
  api/
    routes/         # FastAPI routers (auth, profile, resume, chat, copilot, sessions)
    dependencies.py # FastAPI dependency injection
  core/
    model_factory.py  # Builds LLM instances from agents.yaml config
    database.py
    config.py
  interfaces/       # Abstract base classes for agents and repositories
  models/
    data_models.py  # All Pydantic request/response/domain models
    db_models.py    # SQLAlchemy ORM models
  pipeline/
    pipeline.py        # ResumePipeline (LangGraph: load_profile → analyze_jd → match_skills)
    profile_pipeline.py # ProfileParsePipeline (LangGraph: parse → enrich)
  prompts/          # LLM prompt templates (.txt files)
  repositories/     # Database access layer
  services/         # Pure-Python helpers (KeywordScorer, tier1_checker, ProfileManager)
frontend-vue/       # Vue 3 frontend
agents.yaml         # Model configuration per agent
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 14+
- Google Gemini API key (set `GOOGLE_API_KEY` env var)
- Two Gemini model env vars:
  - `GOOGLE_FLASH_MODEL` — e.g. `gemini-2.0-flash`
  - `GOOGLE_FLASH_LITE_MODEL` — e.g. `gemini-2.0-flash-lite`

## Local Development Setup

### Backend

```bash
# Create and activate virtualenv
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser (for PDF export)
playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env: set DATABASE_URL, GOOGLE_API_KEY, GOOGLE_FLASH_MODEL, GOOGLE_FLASH_LITE_MODEL, SECRET_KEY

# Run database migrations (Alembic)
alembic upgrade head

# Start backend
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend-vue
npm install
npm run dev
# Frontend runs on http://localhost:5173
```

API docs available at `http://localhost:8000/docs`.

## Configuration

All LLM agent model assignments are in [`agents.yaml`](agents.yaml). Each entry specifies the model, temperature, thinking level, and token limits. To switch providers or models, edit this file — no code changes required.

```yaml
agents:
  resume_tailor:
    model: GOOGLE_FLASH_MODEL   # reads from env var
    temperature: 0.2
    thinking_level: low
```

## API Overview

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Register new user |
| POST | `/auth/login` | Get JWT token |
| GET/PUT | `/profile/me` | Get or update master profile |
| POST | `/profile/upload-pdf` | Parse PDF resume |
| POST | `/profile/upload-pdf/confirm` | Confirm and persist parsed draft |
| POST | `/resume/analyze` | Analyze JD and compute skill match |
| POST | `/resume/confirm-generate` | Generate tailored resume draft |
| POST | `/resume/preview-html` | Render draft to HTML |
| POST | `/resume/export-pdf` | Export draft to PDF |
| POST | `/resume/chat/stream` | Streaming chat with resume assistant (SSE) |
| GET | `/sessions` | List resume sessions |
| GET | `/sessions/{id}` | Get session detail with draft |
| PATCH | `/sessions/{id}/draft` | Save manual draft edits |
| POST | `/copilot/diagnose` | Full three-tier resume diagnostic |
| POST | `/copilot/micro-validate` | Single bullet condition check |
| POST | `/copilot/batch-verify` | Verify if edits resolve pending tasks |

## Multi-Agent Architecture

The system implements four distinct multi-agent workflows. Full details are in [`tmp_doc/workflow.md`](tmp_doc/workflow.md).

**Workflow 1 — Profile Import:** `TwoPhaseProfileParser` (Flash Lite x2) + `CodeProfileEnricher` (rule-based), orchestrated by LangGraph.

**Workflow 2 — Resume Generation:** `OllamaJDAnalyzer` → `OllamaSkillMatcher` → `OllamaResumeTailor`, all Flash models, orchestrated by LangGraph (`ResumePipeline`).

**Workflow 3 — Chat Assistant:** `OllamaResumeChatAgent` with internal intent routing. Router (Flash Lite, structured output) dispatches to `local_patch` / `keyword_inject` / `full_diagnose` / `question` handlers. `full_diagnose` reuses the Copilot `DiagnosticAnalyzer`.

**Workflow 4 — Copilot Panel:** `tier1_checker` (rule-based) + `DiagnosticAnalyzer` (Flash) + `MicroValidator` (Flash Lite) + `BatchVerifier` (Flash), orchestrated directly by the API route.

## Deployment

Docker and CI/CD support are planned. See [`tmp_doc/`](tmp_doc/) for architecture documentation.

For manual deployment, the backend requires:
- A PostgreSQL database accessible via `DATABASE_URL`
- Gemini API access via `GOOGLE_API_KEY`
- Playwright Chromium installed in the runtime environment for PDF export
- Frontend static files built via `npm run build` and served via a reverse proxy (nginx) pointing `/api` to the FastAPI backend
