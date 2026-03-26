# Role
You are an expert Python Backend Architect specializing in LLM Agent systems.

# Task
Design and implement the backend for an "LLM-Based Resume Tailoring Assistant" — a multi-user system where each user maintains a personal skill/experience database, submits a Job Description, and receives a tailored resume rendered in LaTeX format via a multi-agent pipeline.

# Core Tech Stack
- Language: Python 3.10+
- Framework: FastAPI
- Data Validation: Pydantic v2 (strictly for all inter-module data contracts and LLM structured responses)
- Database: PostgreSQL (via asyncpg or SQLAlchemy async); JSONB columns for semi-structured resume data
- LLM Integration: Abstracted behind interfaces; concrete implementations call Claude API with structured output (JSON mode / tool use)
- Auth: JWT-based (python-jose + passlib); password hashing via bcrypt

# Project Directory Structure

```
project/
├── app/
│   ├── models/
│   │   ├── data_models.py       # Pipeline Pydantic models
│   │   └── db_models.py         # SQLAlchemy ORM models
│   ├── interfaces/
│   │   └── base.py              # ABCs for all 5 agent modules + LLM client + DB repo
│   ├── agents/
│   │   ├── jd_analyzer.py
│   │   ├── skill_matcher.py
│   │   ├── resume_generator.py
│   │   └── resume_auditor.py
│   ├── services/
│   │   ├── profile_manager.py
│   │   └── auth_service.py
│   ├── repositories/
│   │   ├── user_repository.py
│   │   └── profile_repository.py
│   ├── pipeline/
│   │   └── pipeline.py          # Orchestrator + Generator<->Auditor loop
│   ├── api/
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   ├── profile.py
│   │   │   └── resume.py
│   │   └── dependencies.py
│   └── core/
│       ├── config.py            # Settings via pydantic-settings
│       └── database.py          # Async DB session factory
├── docker-compose.yml
└── main.py
```

# Database Schema

## users table
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| email | VARCHAR UNIQUE | login credential |
| hashed_password | VARCHAR | bcrypt |
| full_name | VARCHAR | |
| created_at | TIMESTAMP | |

## user_profiles table
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK -> users.id | |
| work_experiences | JSONB | list of WorkExperience |
| educations | JSONB | list of Education |
| projects | JSONB | list of Project |
| summary | TEXT | personal summary |
| updated_at | TIMESTAMP | |

## user_skills table
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK -> users.id | |
| category | VARCHAR | e.g. "Programming Languages", "Frameworks" |
| name | VARCHAR | e.g. "Python", "FastAPI" |
| proficiency | VARCHAR | e.g. "expert", "intermediate", "beginner" |

# Pipeline & Module Requirements

## 1. Profile Manager
- **Responsibility:** CRUD for a user's `MasterProfile` (aggregates profile + skills from DB).
- **Interface methods:** `load_master_profile(user_id: UUID) -> MasterProfile`, `save_profile(user_id: UUID, profile: MasterProfile) -> None`
- Reads from `user_profiles` and `user_skills` tables; assembles into a single `MasterProfile` Pydantic model.

## 2. JD Analyzer (Agent)
- **Responsibility:** Parse raw JD text via LLM to extract structured requirements.
- **Input:** `user_id: UUID`, `raw_jd: str`
- **Output:** `JobDescription` Pydantic model containing: `title`, `company`, `hard_requirements: list[str]`, `core_keywords: list[str]`, `soft_skills: list[str]`, `preferred_qualifications: list[str]`

## 3. Skill Matcher (Agent)
- **Responsibility:** LLM-powered comparison of `MasterProfile` vs `JobDescription`.
- **Output:** `MatchingReport` containing: `matched_skills: list[str]`, `missing_skills: list[str]`, `highlighted_experiences: list[str]`, `relevance_notes: str`

## 4. Resume Generator (Agent — "The Writer")
- **Responsibility:** Generate a tailored `DraftResume` in LaTeX format using `MasterProfile` guided by `MatchingReport` and `JobDescription`. Must also accept `AuditFeedback` to rewrite an existing draft.
- **Input:** `MasterProfile`, `JobDescription`, `MatchingReport`, `AuditFeedback` (optional)
- **Output:** `DraftResume` Pydantic model with field `latex_content: str` (complete, compilable LaTeX source)

## 5. Resume Auditor & State Manager (Agent — "The Reviewer")
- **Responsibility:** Evaluate `DraftResume` quality against `JobDescription`; manage the retry loop.
- **Core Mechanism (Dynamic Relaxation):**
  - Track `retry_count` in `PipelineState`.
  - LLM assigns a `score: float` (0.0 - 1.0) and generates structured `AuditFeedback`.
  - If `score >= current_threshold`: mark as approved, return final resume.
  - If `score < current_threshold`: return `AuditFeedback` to route back to Generator.
  - **Fallback formula:** `current_threshold = initial_threshold - (retry_count * decay_per_retry)`, floored at `min_threshold`.
  - Hard stop at `max_retries` regardless of score — return best draft seen so far.

# Pydantic Data Models (data_models.py)

```
UserCreate, UserRead          # auth / user management
WorkExperience, Education, Project  # resume building blocks
MasterProfile                 # aggregated user profile (skill tree + experiences)
JobDescription                # structured JD output from JD Analyzer
MatchingReport                # skill gap analysis output
AuditFeedback                 # reviewer feedback to writer
DraftResume                   # latex_content: str + metadata
PipelineConfig                # initial_threshold, decay_per_retry, min_threshold, max_retries
PipelineState                 # retry_count, best_score, best_draft, status
```

# Deliverables
1. **app/models/data_models.py** — all pipeline Pydantic models listed above
2. **app/models/db_models.py** — SQLAlchemy ORM models for `users`, `user_profiles`, `user_skills`
3. **app/interfaces/base.py** — ABCs for: `IProfileManager`, `IJDAnalyzer`, `ISkillMatcher`, `IResumeGenerator`, `IResumeAuditor`, `ILLMClient`, `IUserRepository`, `IProfileRepository`
4. **app/pipeline/pipeline.py** — `ResumePipeline` orchestrator class with the Generator<->Auditor loop and dynamic threshold logic
5. **app/core/config.py** — `Settings` via pydantic-settings (DB URL, LLM API key, JWT secret, pipeline defaults)
