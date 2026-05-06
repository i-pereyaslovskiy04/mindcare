-- ============================================
-- Migration 003: Media
-- ============================================

-- Центральное хранилище медиафайлов
CREATE TABLE media_files (
    id              INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid            UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    file_name       VARCHAR(255) NOT NULL,
    file_path       VARCHAR(500) NOT NULL,
    file_type       media_file_type NOT NULL,
    mime_type       VARCHAR(100),
    file_size_bytes BIGINT,
    width_px        INT,
    height_px       INT,
    duration_seconds INT,
    thumbnail_path  VARCHAR(500),
    metadata        JSONB DEFAULT '{}',
    uploaded_by     INT REFERENCES users(id) ON DELETE SET NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_media_type ON media_files (file_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_media_uploaded_by ON media_files (uploaded_by);
CREATE INDEX idx_media_metadata ON media_files USING gin (metadata);

-- Альтернативные версии медиафайлов (thumbnail, сжатые и т.д.)
CREATE TABLE media_versions (
    id                INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    original_media_id INT NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    version_type      media_version_type NOT NULL,
    file_path         VARCHAR(500) NOT NULL,
    file_size_bytes   BIGINT,
    width_px          INT,
    height_px         INT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_media_versions_original ON media_versions (original_media_id);
