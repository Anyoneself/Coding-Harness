CREATE TABLE IF NOT EXISTS workspaces (
    id UUID PRIMARY KEY,
    root_path TEXT NOT NULL,
    permission_profile TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS threads (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS turns (
    id UUID PRIMARY KEY,
    thread_id UUID NOT NULL REFERENCES threads(id),
    prompt TEXT NOT NULL,
    status TEXT NOT NULL,
    version BIGINT NOT NULL,
    next_sequence BIGINT NOT NULL,
    budget_json JSONB NOT NULL,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    interrupt_requested_at TIMESTAMPTZ,
    termination_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_turns_one_active_per_thread
ON turns(thread_id)
WHERE status IN ('queued', 'running', 'waiting_approval');

CREATE TABLE IF NOT EXISTS items (
    id UUID PRIMARY KEY,
    turn_id UUID NOT NULL REFERENCES turns(id),
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS turn_events (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    thread_id UUID NOT NULL REFERENCES threads(id),
    turn_id UUID NOT NULL REFERENCES turns(id),
    sequence BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    payload_json JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    UNIQUE(turn_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_turn_events_replay
ON turn_events(turn_id, sequence);

CREATE TABLE IF NOT EXISTS checkpoints (
    id UUID PRIMARY KEY,
    turn_id UUID NOT NULL REFERENCES turns(id),
    phase TEXT NOT NULL,
    last_sequence BIGINT NOT NULL,
    public_state_json JSONB NOT NULL,
    model_calls INTEGER NOT NULL,
    tool_calls INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_latest
ON checkpoints(turn_id, created_at DESC);

CREATE TABLE IF NOT EXISTS context_snapshots (
    id UUID PRIMARY KEY,
    turn_id UUID NOT NULL REFERENCES turns(id),
    sources_json JSONB NOT NULL,
    builder_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS model_calls (
    id UUID PRIMARY KEY,
    turn_id UUID NOT NULL REFERENCES turns(id),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    public_usage_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
