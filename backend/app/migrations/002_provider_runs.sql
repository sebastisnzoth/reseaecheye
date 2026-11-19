-- Versioned migration: provider execution ledger and audit trail.
CREATE TABLE IF NOT EXISTS provider_runs (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    result_count INTEGER NOT NULL DEFAULT 0,
    checked_at TEXT NOT NULL,
    duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_provider_runs_investigation ON provider_runs(investigation_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    owner_hash TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    created_at TEXT NOT NULL,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_owner ON audit_log(owner_hash, created_at DESC);

ALTER TABLE investigations ADD COLUMN exiftool_available INTEGER NOT NULL DEFAULT 0;
