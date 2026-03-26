# Project Tracker

## Completed

### Infrastructure
- [x] PostgreSQL via Docker Compose (`docker-compose.yml`, `init.sql`)
- [x] Async database session factory (`app/core/database.py`)
- [x] Settings via pydantic-settings with `.env` support (`app/core/config.py`)
- [x] JWT auth (register, login, token decode) (`app/services/auth_service.py`)

### Data Layer
- [x] SQLAlchemy ORM models: `users`, `user_profiles`, `user_skills` (`app/models/db_models.py`)
- [x] All Pydantic data models including full pipeline models (`app/models/data_models.py`)
- [x] Repository interfaces + implementations (`app/interfaces/base.py`, `app/repositories/`)

### API Routes
- [x] `POST /auth/register`
- [x] `POST /auth/login`
- [x] `GET /users/me`
- [x] `PUT /users/me`
- [x] `GET /profile`
- [x] `PUT /profile`
- [x] `POST /profile/skills`
- [x] `POST /profile/upload-pdf` — PDF upload → `ProfileParsePipeline` (parse → enrich) → returns `ParsedProfileDraft`
- [x] `POST /profile/upload-pdf/confirm` — append parsed draft to profile
- [x] `POST /resume/analyze` — stage 1: analyze JD + match skills, returns `MatchingPreview` with session_id
- [x] `POST /resume/confirm` — stage 2: user confirms (with optional experience/project + template selection), runs generator + auditor loop
- [x] `POST /resume/compile` — accepts `{ latex_content }`, runs `TectonicCompiler`, returns `application/pdf`
- [x] `POST /resume/generate` — legacy single-shot pipeline entry point (kept for backward compat)
- [x] `GET /templates` — combined global + user templates list
- [x] `GET/POST/DELETE /templates/global` — admin-only global template management
- [x] `GET/POST/DELETE /templates/mine` — user custom template management

### Resume Generation Pipeline
- [x] Prompt files separated into `app/prompts/` (profile_parser, profile_enricher, jd_analyzer, skill_matcher, resume_generator, resume_auditor)
- [x] All agents refactored to LCEL chains (`ChatPromptTemplate | ChatOllama | JsonOutputParser/StrOutputParser`)
- [x] `OllamaJDAnalyzer` — LCEL chain, parses raw JD text into `JobDescription`
- [x] `OllamaSkillMatcher` — LCEL chain, compares `MasterProfile` vs `JobDescription` into `MatchingReport`
- [x] `OllamaResumeGenerator` — LCEL chain, generates LaTeX resume; supports optional `preamble` + `body_example` from template
- [x] `OllamaResumeAuditor` — LCEL chain, scores draft and returns `AuditFeedback` with dynamic threshold
- [x] `ResumePipeline` — split into two LangGraph sub-graphs: `_analysis_graph` (load_profile → analyze_jd → match_skills) and `_generation_graph` (generate ⇄ audit); module-level `_session_store` bridges the two stages
- [x] `analyze_and_preview()` — runs analysis graph, stores `_AnalysisSession` keyed by UUID session_id, returns `MatchingPreview`
- [x] `generate_from_confirmation()` — loads session, applies optional experience/project index filtering, optional template preamble+body_example injection, runs generation graph

### Template Library
- [x] Two separate DB tables: `global_templates` (admin) + `user_templates` (per-user), both with `preamble` + `body_example` columns
- [x] ORM models: `GlobalTemplateORM`, `UserTemplateORM` (`app/models/db_models.py`)
- [x] Pydantic models: `TemplateCreate`, `TemplateRead` with `source: Literal["global","user"]`
- [x] Repositories: `GlobalTemplateRepository`, `UserTemplateRepository` with CRUD + `get_by_id`
- [x] Admin auth: whitelist via `settings.admin_emails`; `get_current_admin_id` dependency
- [x] Template integrated into generation: `/resume/confirm` accepts `template_id` + `template_source`, resolves preamble + body_example from DB, passes both into pipeline
- [x] Frontend: `.tex` file split client-side at `\begin{document}` → preamble + body_example stored separately; body_example used as syntax reference in prompt with explicit prohibition on using template content

### LaTeX Compiler
- [x] `TectonicCompiler` — `subprocess.run` in thread pool executor (Windows SelectorEventLoop workaround)
- [x] `_strip_fences()` — strips markdown code fences from LLM output before writing `.tex`
- [x] `_strip_pdftex_only()` — removes `\input{glyphtounicode}` and `\pdfgentounicode=1` (pdflatex-only, unsupported by tectonic)

### Frontend (Vue 3 + Vite + Naive UI)
- [x] Auth view (register / login)
- [x] Profile view — manual edit + PDF upload → parse → confirm flow
- [x] Generate view — two-stage: JD analyze → match preview + experience/project/template selection → generate
- [x] LaTeX Editor view — Monaco (left) + PDF.js live preview (right), debounced auto-compile, Download PDF
- [x] Templates view — upload `.tex` file (auto-split preamble/body), list global + personal templates, "Use in Editor" button
- [x] `n-message-provider` added to `App.vue`; nav `v-model` → `:value` fix

### Tests
- [x] Auth route tests (`tests/test_auth.py`)
- [x] Users route tests (`tests/test_users.py`)

---

## Known Bugs / Issues

### Pipeline
- [x] **`best_draft` null-guard added**: raises `ValueError` if `best_draft` is `None` after graph completion → HTTP 404.
- [x] **`OllamaResumeGenerator` fence stripping**: `_strip_fences()` in generator + second-layer guard in `TectonicCompiler._run_sync`.
- [x] **Audit `approved` field recomputed deterministically**: overwrites LLM-returned value with `score >= threshold`.
- [x] **tectonic pdflatex compat**: `\input{glyphtounicode}` / `\pdfgentounicode` stripped before compile.
- [x] **Template data leaking into output**: body_example passed to LLM as syntax-only reference; prompt CRITICAL rule prohibits using template content.

### Agents
- [ ] **No retry on JSON parse failure**: malformed JSON from `jd_analyzer`, `skill_matcher`, or `resume_auditor` causes 500. Need parse-retry wrapper.

### Tests
- [ ] **No tests for pipeline routes** (`/resume/analyze`, `/resume/confirm`, `/resume/compile`).
- [ ] **No tests for profile routes** (`/profile/upload-pdf`, `/profile/upload-pdf/confirm`).
- [ ] **No tests for template routes**.
- [ ] **No integration tests** hitting real DB.

### Configuration
- [ ] **Pipeline config defaults duplicated**: `PipelineConfig` hardcoded defaults and `config.py` `pipeline_*` settings can drift.

---

## Not Yet Implemented

- [ ] Resume history storage — persist generated resumes per user to DB
- [ ] Streaming response — SSE or WebSocket for pipeline progress feedback
- [ ] Claude API backend — Ollama is current backend; Claude-based agent implementations needed
