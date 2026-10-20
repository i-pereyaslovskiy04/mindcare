-- ============================================
-- Migration 007: Notifications
-- ============================================

-- Шаблоны уведомлений (без ПДн в тексте!)
CREATE TABLE notification_templates (
    id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code       VARCHAR(100) NOT NULL UNIQUE,
    title      VARCHAR(255) NOT NULL,
    body       TEXT NOT NULL,
    channel    VARCHAR(50) DEFAULT 'web',
    is_active  BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Уведомления пользователей
CREATE TABLE notifications (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    template_id INT REFERENCES notification_templates(id) ON DELETE SET NULL,
    params      JSONB DEFAULT '{}',
    channel     VARCHAR(50) DEFAULT 'web',
    is_read     BOOLEAN DEFAULT FALSE,
    read_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_notifications_user_unread ON notifications (user_id, created_at DESC) WHERE is_read = FALSE;
CREATE INDEX idx_notifications_user ON notifications (user_id, created_at DESC);
