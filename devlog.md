# Dev Log

---

## 2026-03-14

### Completed

#### Infrastructure & Auth
- PostgreSQL via Docker Compose (`docker-compose.yml`, `init.sql`)
- Async SQLAlchemy session factory, pydantic-settings config
- JWT auth: register, login, token decode
- Admin whitelist via `settings.admin_emails`

#### Data Layer
- ORM models: `users`, `user_profiles`, `user_skills`, `global_templates`, `user_templates`
- All Pydantic pipeline models in `data_models.py`
- Repository pattern with interface ABCs (`interfaces/base.py`)

#### Resume Pipeline (Legacy / v1)
- `OllamaJDAnalyzer` — raw JD text → `JobDescription`
- `OllamaSkillMatcher` — `MasterProfile` vs `JobDescription` → `MatchingReport`
- `OllamaResumeGenerator` — LaTeX resume generation with optional template injection
- `OllamaResumeAuditor` — scores draft, returns `AuditFeedback`, drives retry loop
- `ResumePipeline` — split into `_analysis_graph` + `_generation_graph` via LangGraph; session store bridges the two stages
- Dynamic threshold relaxation: `threshold -= decay_per_retry` per retry, floored at `min_threshold`

#### Template Library
- Two DB tables: `global_templates` (admin-only) + `user_templates` (per-user), both with `preamble` + `body_example` columns
- CRUD routes: `GET/POST/DELETE /templates/global`, `GET/POST/DELETE /templates/mine`, `GET /templates`
- Client-side `.tex` split at `\begin{document}` → `preamble` + `body_example` stored separately

#### LaTeX Compiler
- `TectonicCompiler` with thread-pool executor (Windows SelectorEventLoop workaround)
- `_strip_pdftex_only()`: removes `\input{glyphtounicode}` and `\pdfgentounicode=1` (tectonic incompatible)

#### Architecture v2 (JSON-centric pipeline)
- New data models: `TailoredBullet`, `TailoredExperience`, `TailoredProject`, `TailoredResumeDraft`
- `OllamaContentDrafter` — LLM outputs only JSON matching `TailoredResumeDraft`; no LaTeX knowledge
- `TemplateFiller` — Jinja2 engine with custom delimiters (`<< >>`, `<% %>`) to avoid LaTeX `{}` conflict; `latex_escape` filter
- `classic.tex.j2` — Jake's Resume style Jinja2 template
- `V2ResumePipeline` — LangGraph: `draft` → `render` → `audit` → conditional loop; returns `TailoredResumeDraft`
- `/resume/confirm` wired to `V2ResumePipeline`; returns `TailoredResumeDraft` instead of raw LaTeX
- `/resume/render` — accepts `TailoredResumeDraft` + optional template; Jinja2 render → compile to PDF or return LaTeX source

#### API Routes (full list)
- `POST /auth/register`, `POST /auth/login`
- `GET /users/me`, `PUT /users/me`
- `GET /profile`, `PUT /profile`, `POST /profile/skills`
- `POST /profile/upload-pdf` → `ProfileParsePipeline` → `ParsedProfileDraft`
- `POST /profile/upload-pdf/confirm`
- `POST /resume/analyze` — JD analysis + skill match, returns `MatchingPreview` + session_id
- `POST /resume/confirm` — V2Pipeline: draft→render→audit loop, returns `TailoredResumeDraft`
- `POST /resume/render` — `TailoredResumeDraft` → Jinja2 → PDF or LaTeX source
- `POST /resume/compile` — raw LaTeX → PDF
- `POST /resume/generate` — legacy single-shot endpoint (kept for backward compat)
- `GET/POST/DELETE /templates/global` (admin)
- `GET/POST/DELETE /templates/mine` (user)
- `GET /templates`

#### Frontend (Vue 3 + Vite + Naive UI)
- Auth view (register / login)
- Profile view — manual edit + PDF upload → parse → confirm flow
- Generate view:
  - Stage 1: JD input
  - Stage 2: match preview, experience/project checkbox selection, template picker, pipeline config
  - Stage 3: structured `TailoredResumeDraft` editor (summary, experiences with bullets, education, projects, skills); "Render PDF" and "Get LaTeX" actions
- LaTeX Editor view — Monaco (left) + PDF.js live preview (right), debounced auto-compile
- Templates view — upload `.tex` (auto-split), list global + personal templates, delete, "Use in Editor"

---

## TODO

### Critical — V2 correctness

- [ ] **`template_type` column** (`global_templates` + `user_templates`)
  - Add `template_type VARCHAR(10) DEFAULT 'jinja2'` to both tables in `init.sql` + ORM
  - User-uploaded `.tex` templates should be tagged `raw`; global `.tex.j2` templates tagged `jinja2`
  - `/resume/confirm` and `/resume/render`: if `template_type == 'raw'`, skip `TemplateFiller` and fall back to default Jinja2 template (or reject with 422)
  - Frontend: show template type badge; warn user if selected template is `raw` (not usable in v2 flow)

- [ ] **Validate `content_drafter.txt` prompt end-to-end**
  - Run full V2 pipeline once; verify LLM output parses cleanly into `TailoredResumeDraft`
  - Ensure `TailoredBullet.highlighted` field is present and correct
  - Tighten prompt schema section if LLM omits optional fields or adds extra keys

- [ ] **JSON parse retry on all agents**
  - `OllamaContentDrafter`, `OllamaJDAnalyzer`, `OllamaSkillMatcher`, `OllamaResumeAuditor` all fail hard on `json.loads()` error
  - Add a shared `_parse_with_retry(raw: str, model: type[BaseModel], max_retries: int = 2)` utility
  - On parse failure: log the raw output, re-invoke the chain with an error correction hint, retry up to `max_retries`

### High — User value

- [ ] **Resume history storage**
  - New DB table: `resume_history` (`id UUID PK`, `user_id FK`, `draft JSONB`, `template_id UUID nullable`, `created_at TIMESTAMPTZ`)
  - `POST /resume/history` — save current `TailoredResumeDraft`
  - `GET /resume/history` — paginated list per user
  - `GET /resume/history/{id}` — fetch single draft
  - Frontend: "Save Draft" button in Stage 3; history list view

- [ ] **Pipeline progress feedback (SSE)**
  - Current: generate button spins with no feedback during multi-retry loop
  - Add `GET /resume/stream/{session_id}` SSE endpoint; emit node-level events (`draft_start`, `audit_score`, `retry`, `done`)
  - Frontend: replace spinner with live log / progress bar during generation

### Medium — Reliability

- [ ] **`PipelineConfig` defaults deduplication**
  - Defaults are hardcoded in `PipelineConfig` Pydantic model AND in frontend reactive config
  - Move authoritative defaults to `app/core/config.py` `Settings`; expose via `GET /resume/config/defaults`

- [ ] **Session store TTL / cleanup**
  - `_session_store` in `pipeline.py` is a plain module-level dict; sessions are never evicted if user abandons flow
  - Add TTL (e.g. 30 min) with a background cleanup task or switch to Redis

### Low — Test coverage

- [ ] `POST /resume/analyze` + `POST /resume/confirm` integration tests
- [ ] `POST /profile/upload-pdf` + confirm tests
- [ ] Template route tests (global + user CRUD)
- [ ] `TemplateFiller` unit tests (escape filter, section rendering)
- [ ] `V2ResumePipeline` unit tests with mocked drafter/auditor

### Future (documented, not scheduled)

- [ ] **Claude API backend** — replace Ollama with Claude (`claude-opus-4-6` / `claude-sonnet-4-6`); implement `ClaudeContentDrafter`, `ClaudeResumeAuditor` behind existing interfaces
- [ ] **Floating chat agent** — user selects text in Stage 3 editor, opens dialog, agent refines targeted field; `POST /resume/refine-field` endpoint
- [ ] **Export formats** — DOCX output in addition to PDF
- [ ] **Multi-language support** — resume in languages other than English
