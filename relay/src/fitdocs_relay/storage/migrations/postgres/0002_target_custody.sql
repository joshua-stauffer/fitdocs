-- 0002_target_custody (PostgreSQL): a principal's connection to a provider target
-- and the provider-call budget counts.
-- Times are bigint epoch seconds UTC.

CREATE TABLE target_connections (
    principal_id TEXT NOT NULL
        REFERENCES principals (principal_id) ON DELETE CASCADE,
    target TEXT NOT NULL,
    account_key TEXT NOT NULL,
    access_sealed TEXT NOT NULL,
    refresh_sealed TEXT,
    access_expires_at BIGINT,
    generation BIGINT NOT NULL,
    lease_id TEXT,
    lease_until BIGINT,
    token_id TEXT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    PRIMARY KEY (principal_id, target),
    UNIQUE (target, account_key)
);

CREATE TABLE budget_counts (
    key TEXT NOT NULL,
    window_start BIGINT NOT NULL,
    count BIGINT NOT NULL,
    window_end BIGINT NOT NULL,
    principal_id TEXT
        REFERENCES principals (principal_id) ON DELETE CASCADE,
    PRIMARY KEY (key, window_start)
);

CREATE INDEX budget_counts_window_end_idx ON budget_counts (window_end);
