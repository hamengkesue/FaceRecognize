-- ==============================================================
-- Personal Laptop Face Guard Database Initialization
-- ==============================================================

-- 1. Enable pgvector extension for 512-D ArcFace facial embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Owner Facial Embeddings Table
CREATE TABLE IF NOT EXISTS owner_embeddings (
    id SERIAL PRIMARY KEY,
    pose_label VARCHAR(50) NOT NULL,
    embedding vector(512) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Fast Cosine Similarity HNSW index
CREATE INDEX IF NOT EXISTS idx_owner_embedding_cosine 
ON owner_embeddings USING hnsw (embedding vector_cosine_ops);

-- 3. Security Events & Intruder Evidence Table
CREATE TABLE IF NOT EXISTS security_logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(30) NOT NULL,       -- 'INTRUDER_ALERT', 'SNOOPING_WARNING', 'USER_AWAY'
    similarity_score REAL,                 -- Highest similarity score with owner (0.0 - 1.0)
    intruder_embedding vector(512),        -- Intruder 512-D embedding to identify repeat offenders
    repeat_offender_of INT REFERENCES security_logs(id) ON DELETE SET NULL,
    snapshot_path TEXT,                    -- Local disk path of evidence snapshot
    is_notified BOOLEAN DEFAULT FALSE,     -- Status of Telegram alert delivery
    detected_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Index for log lookups and repeat offender detection
CREATE INDEX IF NOT EXISTS idx_security_logs_detected_at 
ON security_logs (event_type, detected_at DESC);

-- 4. Dynamic System Configurations Table
CREATE TABLE IF NOT EXISTS system_configs (
    config_key VARCHAR(50) PRIMARY KEY,
    config_value VARCHAR(100) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Seed default configuration parameters
INSERT INTO system_configs (config_key, config_value) VALUES
('similarity_threshold', '0.50'),
('intruder_grace_seconds', '3.0'),
('snooping_grace_seconds', '2.0'),
('away_lock_seconds', '30.0'),
('idle_poll_interval', '2.5')
ON CONFLICT (config_key) DO NOTHING;

