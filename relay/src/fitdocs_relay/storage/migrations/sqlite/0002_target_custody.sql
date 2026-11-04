-- 0002_target_custody (SQLite): a principal's connection to a provider target
-- and the provider-call budget counts.
-- Times are integer epoch seconds UTC.

CREATE TABLE target_connections (
    principal_id TEXT NOT NULL
        REFERENCES principals (principal_id) ON DELETE CASCADE,
    target TEXT NOT NULL,
    account_key TEXT NOT NULL,
    access_sealed TEXT NOT NULL,
    refresh_sealed TEXT,
    access_expires_at INTEGER,
    generation INTEGER NOT NULL,
    lease_id TEXT,
    lease_until INTEGER,
    token_id TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (principal_id, target),
    UNIQUE (target, account_key)
);

CREATE TABLE budget_counts (
    key TEXT NOT NULL,
    window_start INTEGER NOT NULL,
    count INTEGER NOT NULL,
    window_end INTEGER NOT NULL,
    principal_id TEXT
        REFERENCES principals (principal_id) ON DELETE CASCADE,
    PRIMARY KEY (key, window_start)
);

CREATE INDEX budget_counts_window_end_idx ON budget_counts (window_end);
