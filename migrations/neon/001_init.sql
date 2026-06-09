-- Neon (Postgres) schema for Versiful long-term memory.
-- Applies to each environment's Neon project (versiful-dev / staging / prod).
-- Idempotent: safe to re-run.

-- Enable pgvector once per database
CREATE EXTENSION IF NOT EXISTS vector;

-- Long-term structured facts the agent learns about the user
CREATE TABLE IF NOT EXISTS user_memories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,    -- Cognito sub; joins to the DynamoDB users item (no FK)
    kind            TEXT NOT NULL,    -- life_event | struggle | relationship | preference | spiritual_state | goal
    summary         TEXT NOT NULL,    -- "Father diagnosed with cancer, surgery scheduled"
    detail          TEXT,             -- optional longer note
    people          JSONB,            -- ["dad"], ["wife Sarah"]
    embedding       vector(1536),     -- OpenAI text-embedding-3-small; powers semantic recall
    salience        REAL NOT NULL DEFAULT 0.5,   -- 0-1, decays/boosts over time
    status          TEXT NOT NULL DEFAULT 'active', -- active | resolved | archived
    source          TEXT,             -- chat | sms | manual | checkin
    source_msg_id   TEXT,             -- DynamoDB chat_messages id, if applicable
    event_date      DATE,             -- if the memory references a date (surgery Thursday)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_referenced_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_memories_user_active ON user_memories(user_id, status, salience DESC);
CREATE INDEX IF NOT EXISTS idx_memories_embedding ON user_memories USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS reflections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,    -- Cognito sub; joins to the DynamoDB users item (no FK)
    content         TEXT NOT NULL,    -- the takeaway / journal entry
    embedding       vector(1536),     -- OpenAI text-embedding-3-small; powers semantic recall
    source          TEXT NOT NULL,    -- auto_summary | manual | reading_plan
    session_id      TEXT,             -- DynamoDB chat_sessions session id (no FK)
    verse_reference TEXT,
    mood            TEXT,             -- optional emoji/tag
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reflections_user ON reflections(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reflections_embedding ON reflections USING hnsw (embedding vector_cosine_ops);
