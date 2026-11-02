-- 0001_initial (SQLite): the version table, principals, tokens, rate counts
-- and extension records. Times are integer epoch seconds UTC.

CREATE TABLE relay_schema (
    version INTEGER NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at INTEGER NOT NULL
);

CREATE TABLE principals (
    principal_id TEXT NOT NULL PRIMARY KEY,
    label TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE tokens (
    token_id TEXT NOT NULL PRIMARY KEY,
    principal_id TEXT NOT NULL
        REFERENCES principals (principal_id) ON DELETE CASCADE,
    verifier TEXT NOT NULL,
    label TEXT,
    created_at INTEGER NOT NULL,
    revoked_at INTEGER
);

CREATE INDEX tokens_principal_id_idx ON tokens (principal_id);

CREATE TABLE rate_counts (
    key TEXT NOT NULL,
    window_start INTEGER NOT NULL,
    count INTEGER NOT NULL,
    window_end INTEGER NOT NULL,
    PRIMARY KEY (key, window_start)
);

CREATE INDEX rate_counts_window_end_idx ON rate_counts (window_end);

CREATE TABLE records (
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value BLOB NOT NULL,
    expires_at INTEGER NOT NULL,
    PRIMARY KEY (namespace, key)
);

CREATE INDEX records_expires_at_idx ON records (expires_at);
