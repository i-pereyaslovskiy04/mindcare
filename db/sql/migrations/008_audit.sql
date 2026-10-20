-- ============================================
-- Migration 008: Audit (партиционированные таблицы)
-- ============================================

-- 1. audit_log — универсальный журнал действий
CREATE TABLE audit_log (
    id             BIGINT GENERATED ALWAYS AS IDENTITY,
    user_id        INT REFERENCES users(id) ON DELETE SET NULL,
    user_role      VARCHAR(50),
    event_type     VARCHAR(100) NOT NULL,
    entity_type    VARCHAR(100),
    entity_id      INT,
    description    TEXT,
    metadata       JSONB DEFAULT '{}',
    ip_address     INET,
    user_agent     TEXT,
    session_id     VARCHAR(255),
    request_url    VARCHAR(500),
    request_method VARCHAR(10),
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE audit_log_2026_01 PARTITION OF audit_log FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE audit_log_2026_02 PARTITION OF audit_log FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
CREATE TABLE audit_log_2026_03 PARTITION OF audit_log FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
CREATE TABLE audit_log_2026_04 PARTITION OF audit_log FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE audit_log_2026_05 PARTITION OF audit_log FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE audit_log_2026_06 PARTITION OF audit_log FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE audit_log_2026_07 PARTITION OF audit_log FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE audit_log_2026_08 PARTITION OF audit_log FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE audit_log_2026_09 PARTITION OF audit_log FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE audit_log_2026_10 PARTITION OF audit_log FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE audit_log_2026_11 PARTITION OF audit_log FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE audit_log_2026_12 PARTITION OF audit_log FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');

CREATE INDEX idx_audit_user ON audit_log (user_id, created_at DESC);
CREATE INDEX idx_audit_event ON audit_log (event_type, created_at DESC);
CREATE INDEX idx_audit_entity ON audit_log (entity_type, entity_id) WHERE entity_id IS NOT NULL;
CREATE INDEX idx_audit_metadata ON audit_log USING gin (metadata);

-- 2. auth_log — журнал аутентификации
CREATE TABLE auth_log (
    id             BIGINT GENERATED ALWAYS AS IDENTITY,
    user_id        INT REFERENCES users(id) ON DELETE SET NULL,
    user_email     VARCHAR(255),
    event          auth_event NOT NULL,
    success        BOOLEAN NOT NULL DEFAULT TRUE,
    failure_reason VARCHAR(255),
    ip_address     INET,
    user_agent     TEXT,
    session_id     VARCHAR(255),
    mfa_method     VARCHAR(20),
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE auth_log_2026_01 PARTITION OF auth_log FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE auth_log_2026_02 PARTITION OF auth_log FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
CREATE TABLE auth_log_2026_03 PARTITION OF auth_log FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
CREATE TABLE auth_log_2026_04 PARTITION OF auth_log FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE auth_log_2026_05 PARTITION OF auth_log FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE auth_log_2026_06 PARTITION OF auth_log FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE auth_log_2026_07 PARTITION OF auth_log FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE auth_log_2026_08 PARTITION OF auth_log FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE auth_log_2026_09 PARTITION OF auth_log FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE auth_log_2026_10 PARTITION OF auth_log FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE auth_log_2026_11 PARTITION OF auth_log FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE auth_log_2026_12 PARTITION OF auth_log FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');

CREATE INDEX idx_auth_user ON auth_log (user_id, created_at DESC);
CREATE INDEX idx_auth_ip ON auth_log (ip_address, created_at DESC);
CREATE INDEX idx_auth_failures ON auth_log (ip_address, created_at DESC) WHERE success = FALSE;

-- 3. data_change_log — журнал изменений данных (152-ФЗ)
CREATE TABLE data_change_log (
    id             BIGINT GENERATED ALWAYS AS IDENTITY,
    actor_id       INT REFERENCES users(id) ON DELETE SET NULL,
    actor_role     VARCHAR(50),
    table_name     VARCHAR(100) NOT NULL,
    record_id      INT,
    operation      VARCHAR(10) NOT NULL,
    old_values     JSONB,
    new_values     JSONB,
    changed_fields TEXT[],
    ip_address     INET,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE data_change_log_2026_01 PARTITION OF data_change_log FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE data_change_log_2026_02 PARTITION OF data_change_log FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
CREATE TABLE data_change_log_2026_03 PARTITION OF data_change_log FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
CREATE TABLE data_change_log_2026_04 PARTITION OF data_change_log FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE data_change_log_2026_05 PARTITION OF data_change_log FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE data_change_log_2026_06 PARTITION OF data_change_log FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE data_change_log_2026_07 PARTITION OF data_change_log FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE data_change_log_2026_08 PARTITION OF data_change_log FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE data_change_log_2026_09 PARTITION OF data_change_log FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE data_change_log_2026_10 PARTITION OF data_change_log FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE data_change_log_2026_11 PARTITION OF data_change_log FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE data_change_log_2026_12 PARTITION OF data_change_log FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');

CREATE INDEX idx_dcl_actor ON data_change_log (actor_id, created_at DESC);
CREATE INDEX idx_dcl_table ON data_change_log (table_name, record_id);
CREATE INDEX idx_dcl_operation ON data_change_log (operation, created_at DESC);
