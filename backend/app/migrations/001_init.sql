-- ImageTrace OSINT - initial schema (SQLite / PostgreSQL-compatible types)
CREATE TABLE IF NOT EXISTS investigations (
    id TEXT PRIMARY KEY,
    owner_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    stage TEXT NOT NULL DEFAULT 'validacion',
    progress INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    lang TEXT NOT NULL DEFAULT 'es',
    source_kind TEXT NOT NULL,
    source_url TEXT,
    original_filename TEXT,
    mime TEXT,
    size_bytes INTEGER,
    sha256 TEXT,
    phash TEXT,
    width INTEGER,
    height INTEGER,
    keywords TEXT,
    allow_gps INTEGER NOT NULL DEFAULT 0,
    allow_external INTEGER NOT NULL DEFAULT 1,
    retention_hours INTEGER NOT NULL DEFAULT 24,
    expires_at TEXT,
    asset_original TEXT,
    asset_display TEXT,
    asset_diff TEXT,
    metadata_json TEXT,
    forensics_json TEXT,
    ocr_json TEXT,
    report_json TEXT,
    report_pdf TEXT,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_investigations_owner ON investigations(owner_hash, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_investigations_sha ON investigations(sha256);
CREATE INDEX IF NOT EXISTS idx_investigations_expires ON investigations(expires_at);

CREATE TABLE IF NOT EXISTS matches (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    source_url TEXT,
    page_url TEXT,
    domain TEXT,
    title TEXT,
    published_at TEXT,
    published_at_note TEXT,
    thumbnail_url TEXT,
    local_thumbnail TEXT,
    image_url TEXT,
    match_type TEXT NOT NULL,
    evidence_level TEXT NOT NULL,
    similarity REAL,
    phash_distance INTEGER,
    sha256_match INTEGER NOT NULL DEFAULT 0,
    metric_explanation TEXT,
    license TEXT,
    notes TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_matches_investigation ON matches(investigation_id);

CREATE TABLE IF NOT EXISTS index_entries (
    id TEXT PRIMARY KEY,
    owner_hash TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    phash TEXT,
    width INTEGER,
    height INTEGER,
    label TEXT,
    source_url TEXT,
    asset_path TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_index_owner ON index_entries(owner_hash);
CREATE INDEX IF NOT EXISTS idx_index_sha ON index_entries(sha256);
