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
| LLM Provider | Google Gemini (Flash / Flash Lite) by default; OpenAI or Ollama selectable per agent |
| PDF Parsing | PyMuPDF |
| Frontend | Vue 3, Vite, Naive UI, TypeScript |
| Auth | JWT (python-jose), bcrypt (pwdlib) |
| PDF Export | Playwright (headless Chromium) |
| Packaging | Docker Compose; nginx serves the built frontend and proxies the API |

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
    pipeline.py        # ResumePipeline (LangGraph: load_profile → analyze_jd → select_top_n → match_skills)
    profile_pipeline.py # ProfileParsePipeline (LangGraph: parse → enrich → summarize)
  prompts/          # LLM prompt templates (.txt files)
  repositories/     # Database access layer
  services/         # Non-agent helpers (KeywordScorer, tier1_checker, ProfileManager,
                    # ResumeRenderer, PdfExporter)
frontend-vue/       # Vue 3 frontend
  Dockerfile        # vite build, served by nginx
  nginx.conf        # SPA fallback plus /api proxy to the API container
agents.yaml         # Model configuration per agent
init.sql            # Database schema (no migration tool; see below)
Dockerfile          # API image: Python 3.12 plus Playwright Chromium
docker-compose.yml  # postgres, and api + web behind the "app" profile
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 14+ (or Docker, to run the bundled `postgres:16-alpine` service)
- An API key for one LLM provider. The default is Google Gemini:
  - `GOOGLE_API_KEY`
  - `GOOGLE_FLASH_MODEL` — e.g. `gemini-2.0-flash`
  - `GOOGLE_FLASH_LITE_MODEL` — e.g. `gemini-2.0-flash-lite`

To use OpenAI instead of Gemini, set `LLM_PROVIDER=openai` plus `OPENAI_API_KEY`,
`OPENAI_FAST_MODEL` and `OPENAI_SMART_MODEL`. Every agent is remapped through the
`openai.agents` section of [`agents.yaml`](agents.yaml); no code changes are needed.
See [`.env.example`](.env.example) for the full list of variables.

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
# Edit .env: set POSTGRES_*, DATABASE_URL, JWT_SECRET_KEY, GOOGLE_API_KEY,
# GOOGLE_FLASH_MODEL, GOOGLE_FLASH_LITE_MODEL

# Start PostgreSQL alone. On first run the container executes init.sql
# automatically, which creates every table. The API and frontend images sit
# behind the "app" profile, so they are not started here — see Deployment.
docker compose up -d

# Start backend
uvicorn main:app --reload --port 8000
```

### Database schema

This project has no migration tool. [`init.sql`](init.sql) is the single source of
truth for the schema and is kept in sync with the SQLAlchemy models in
[`app/models/db_models.py`](app/models/db_models.py) by hand.

`docker compose up` applies it only when the `pgdata` volume is created. Against an
existing or hosted database, apply it yourself:

```bash
# psql does not understand the "+asyncpg" dialect prefix used by DATABASE_URL.
psql "postgresql://USER:PASSWORD@HOST:5432/resume_db" -f init.sql
```

Every statement is `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`, so
re-running it is safe. It contains schema only — no seed data.

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
| GET | `/health` | Liveness probe; does not touch the database |
| POST | `/auth/register` | Register new user |
| POST | `/auth/login` | Get JWT token |
| GET/PUT | `/users/me` | Get or update the current account |
| GET/PUT | `/profile/` | Get or update master profile |
| POST/PUT | `/profile/skills` | Append to or replace the skill list |
| POST | `/profile/upload-pdf` | Parse PDF resume |
| POST | `/profile/upload-pdf/confirm` | Confirm and persist parsed draft |
| POST | `/profile/chat/stream` | Streaming chat for profile editing (SSE) |
| POST | `/profile/inject-mock` | Load a sample profile (development helper) |
| POST | `/resume/analyze` | Analyze JD and compute skill match |
| POST | `/resume/confirm` | Generate tailored resume draft |
| POST | `/resume/tailor-one` | Re-tailor a single section |
| POST | `/resume/tailor-full` | Re-tailor the whole draft |
| POST | `/resume/preview-html` | Render draft to HTML |
| POST | `/resume/export-pdf` | Export draft to PDF |
| POST | `/resume/chat/stream` | Streaming chat with resume assistant (SSE) |
| POST | `/resume/chat` | Non-streaming chat, returns the patch in one response |
| GET | `/resume/chat/{session_id}` | Chat history for a session |
| POST | `/resume/chat/{session_id}/undo` | Revert the last chat-applied patch |
| GET | `/sessions` | List resume sessions |
| GET | `/sessions/{id}` | Get session detail with draft |
| PATCH | `/sessions/{id}/draft` | Save manual draft edits |
| DELETE | `/sessions/{id}` | Delete a session |
| POST | `/copilot/diagnose` | Full three-tier resume diagnostic |
| POST | `/copilot/micro-validate` | Single bullet condition check |
| POST | `/copilot/batch-verify` | Verify if edits resolve pending tasks |

`/resume/render`, `/resume/compile` and the `/templates/*` routes are registered but
marked deprecated: they belong to the retired LaTeX/Tectonic rendering path and are
superseded by `/resume/preview-html` and `/resume/export-pdf`.

## Multi-Agent Architecture

The system implements four distinct multi-agent workflows.

**Workflow 1 — Profile Import:** LangGraph `ProfileParsePipeline` runs `parse` → `enrich` →
`summarize`: `TwoPhaseProfileParser` (one header-detection call on Flash, because every
downstream split depends on it, then four parallel section calls on Flash Lite), then
`CodeProfileEnricher` (rule-based, no LLM), then `ExperienceSummarizer` (Flash).

**Workflow 2 — Resume Generation:** LangGraph `ResumePipeline` runs `load_profile` →
`analyze_jd` → `select_top_n` → `match_skills`, using `OllamaJDAnalyzer`, `TopNSelector`
and `OllamaSkillMatcher` (all Flash). Tailoring is a separate step: `POST /resume/confirm`
invokes `OllamaResumeTailor` directly, outside the graph.

**Workflow 3 — Chat Assistant:** `OllamaResumeChatAgent` with internal intent routing. Router (Flash Lite, structured output) dispatches to `local_patch` / `keyword_inject` / `full_diagnose` / `question` handlers. `full_diagnose` reuses the Copilot `DiagnosticAnalyzer`.

**Workflow 4 — Copilot Panel:** `tier1_checker` (rule-based) + `DiagnosticAnalyzer` (Flash) + `MicroValidator` (Flash Lite) + `BatchVerifier` (Flash), orchestrated directly by the API route.

The `Ollama*` class-name prefix is historical — those agents were first written against a
local Ollama server. They now build their model through `ModelFactory` like every other
agent, so the prefix says nothing about which provider is in use.

## What leaves your machine

Uploading a resume sends its text to whichever LLM provider is configured. The exposure
is narrower than it looks, and worth knowing before you point this at a real resume:

| Call | Sees |
|---|---|
| Section header detection | The **entire resume text**, including the contact block at the top |
| The four section parsers | Only their own section body |
| JD analysis, matching, tailoring | Employers, schools, project names, bullet text |

The contact block is the only place direct identifiers appear, and only the header
detector sees it — content above the first section header is discarded during splitting,
which is also why `ParsedProfileDraft` carries no contact fields. Contact details are
attached to a draft after the model returns, never sent to it.

`LANGCHAIN_TRACING_V2=true` changes this picture completely: it uploads the prompt and
response of every LangChain call to LangSmith, so all of the above is retained by a second
third party. It is off in [`.env.example`](.env.example); keep it off unless you are
debugging.

To keep everything local, set `LLM_PROVIDER=ollama` and point `base_url` in
[`agents.yaml`](agents.yaml) at your Ollama server. No resume text then leaves the machine.

## Deployment

### Running the whole stack in Docker

The `app` profile adds the API and the frontend to the database service. Without it,
`docker compose up -d` starts PostgreSQL alone, which is what local development wants.

```bash
cp .env.example .env
# Edit .env: POSTGRES_*, JWT_SECRET_KEY, and one provider's API key.
# DATABASE_URL is overridden by compose and does not need to be correct here.

docker compose --profile app up -d --build
```

| Service | Image | Published on |
|---|---|---|
| `postgres` | `postgres:16-alpine` | 5432 |
| `api` | built from [`Dockerfile`](Dockerfile) — Python 3.12 + Playwright Chromium | 8000 |
| `web` | built from [`frontend-vue/Dockerfile`](frontend-vue/Dockerfile) — vite build served by nginx | 5173 |

The app is then on `http://localhost:5173`. nginx serves the SPA and proxies `/api/` to
`api:8000`, stripping the prefix exactly as the vite dev server does, so the browser makes
same-origin requests and the frontend needs no build-time API URL.

`api` waits for the database healthcheck before starting, and `DATABASE_URL` is rewritten
by compose to reach `postgres` by service name — the value in `.env` is only used when you
run the backend outside Docker.

### Deploying without compose

- A PostgreSQL database reachable via `DATABASE_URL`, with [`init.sql`](init.sql) applied
- Gemini API access via `GOOGLE_API_KEY` (or OpenAI via `LLM_PROVIDER=openai`)
- `DEBUG=false`, a generated `JWT_SECRET_KEY`, and `CORS_ORIGINS` listing the frontend
  origin — the app refuses to start if the secret is left at its default or `CORS_ORIGINS`
  contains `*`
- Playwright Chromium in the runtime environment for PDF export (the image installs it)
- `GET /health` is a database-free liveness probe

There is no CI pipeline yet.
