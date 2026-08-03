CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email            VARCHAR(255) UNIQUE NOT NULL,
    hashed_password  VARCHAR(255) NOT NULL,
    full_name        VARCHAR(255) NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_profiles (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    work_experiences JSONB NOT NULL DEFAULT '[]',
    educations       JSONB NOT NULL DEFAULT '[]',
    projects         JSONB NOT NULL DEFAULT '[]',
    summary          TEXT,
    base_resume      JSONB DEFAULT NULL,
    contact_info     JSONB DEFAULT NULL,
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id)
);

CREATE TABLE IF NOT EXISTS user_skills (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category    VARCHAR(100) NOT NULL,
    name        VARCHAR(100) NOT NULL,
    proficiency VARCHAR(20) NOT NULL CHECK (proficiency IN ('expert', 'intermediate', 'beginner'))
);

CREATE TABLE IF NOT EXISTS global_templates (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name         VARCHAR(120) NOT NULL,
    industry     VARCHAR(80),
    style_tag    VARCHAR(80),
    description  TEXT,
    preamble     TEXT NOT NULL,
    body_example TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_templates (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         VARCHAR(120) NOT NULL,
    industry     VARCHAR(80),
    style_tag    VARCHAR(80),
    description  TEXT,
    preamble     TEXT NOT NULL,
    body_example TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS resume_sessions (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    jd_text                     TEXT NOT NULL,
    profile_snapshot_json       JSONB,
    jd_json                     JSONB,
    matching_report_json        JSONB,
    match_score                 FLOAT,
    job_title                   VARCHAR(255),
    company                     VARCHAR(255),
    selected_experience_indices JSONB,
    selected_project_indices    JSONB,
    template_id                 UUID,
    template_source             VARCHAR(10),
    pipeline_config_json        JSONB,
    tailored_draft_json         JSONB,
    status                      VARCHAR(20) NOT NULL DEFAULT 'analyzing'
                                    CHECK (status IN ('analyzing','analyzed','generating','draft_ready','failed')),
    error_message               TEXT,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resume_sessions_user_id ON resume_sessions (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS session_chat_messages (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  UUID NOT NULL REFERENCES resume_sessions(id) ON DELETE CASCADE,
    role        VARCHAR(10) NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    scope_path  VARCHAR(200),
    scope_label VARCHAR(200),
    patch       JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_chat_session_id ON session_chat_messages (session_id, created_at ASC);
