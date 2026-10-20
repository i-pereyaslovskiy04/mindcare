-- =====================================================================
-- РџРћР›РќРђРЇ РЎРҐР•РњРђ Р‘РђР—Р« Р”РђРќРќР«РҐ
-- РџСЂРѕРµРєС‚: В«РџСЃРёС…РѕР»РѕРіРёС‡РµСЃРєР°СЏ РїРѕРјРѕС‰СЊ РІ Р”РѕРЅР“РЈВ»
-- РЎРЈР‘Р”: PostgreSQL 15+
-- Р”Р°С‚Р°: 2026-05-06
--
-- РЎРѕР·РґР°РЅРёРµ Р‘Р”:
--   createdb -U postgres dongu_psychology_portal
--   psql -U postgres -d dongu_psychology_portal -f full_schema.sql
-- =====================================================================
-- ============================================
-- Migration 001: Extensions & Custom Types
-- Психологическая помощь в ДонГУ
-- PostgreSQL 15+
-- ============================================

-- Расширения
CREATE EXTENSION IF NOT EXISTS "pgcrypto";    -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "btree_gist";  -- EXCLUDE constraints (предотвращение пересечений слотов)

-- ============================================
-- Пользовательские ENUM-типы
-- ============================================

-- Модальность консультации
CREATE TYPE appointment_modality AS ENUM (
    'in_person',  -- очно
    'video',      -- видеозвонок
    'phone',      -- телефон
    'chat'        -- чат
);

-- Статус записи на консультацию
CREATE TYPE appointment_status AS ENUM (
    'scheduled',    -- запланирована
    'confirmed',    -- подтверждена
    'in_progress',  -- идёт
    'completed',    -- завершена
    'canceled',     -- отменена
    'no_show'       -- неявка
);

-- Статус терапевтического взаимодействия
CREATE TYPE engagement_status AS ENUM (
    'active',       -- активно
    'paused',       -- приостановлено
    'completed',    -- завершено
    'transferred'   -- передано другому психологу
);

-- Тип вопроса теста
CREATE TYPE question_type AS ENUM (
    'single_choice',    -- один вариант
    'multiple_choice',  -- несколько вариантов
    'scale',            -- шкала (1-10 и т.п.)
    'free_text'         -- свободный ответ
);

-- Тип медиафайла
CREATE TYPE media_file_type AS ENUM ('image', 'video', 'audio', 'document');

-- Роль медиа у вопроса
CREATE TYPE media_role_question AS ENUM ('main', 'supplementary', 'background');

-- Роль медиа у варианта ответа
CREATE TYPE media_role_option AS ENUM ('icon', 'preview', 'full');

-- Версия медиафайла
CREATE TYPE media_version_type AS ENUM ('thumbnail', 'small', 'medium', 'large', 'compressed');

-- Тип заметки сессии
CREATE TYPE session_note_type AS ENUM ('soap', 'progress', 'intake', 'discharge', 'general');

-- Видимость вопроса в Q&A
CREATE TYPE qa_visibility AS ENUM (
    'private',           -- только автор и психолог
    'public_anonymous',  -- публично, анонимно
    'public_named'       -- публично, с именем
);

-- Статус вопроса в Q&A
CREATE TYPE qa_status AS ENUM ('pending', 'assigned', 'answered', 'published', 'archived');

-- Тип события аутентификации
CREATE TYPE auth_event AS ENUM ('login', 'logout', 'failed_login', 'password_reset', 'register', 'mfa_challenge');

-- Тип исключения в расписании
CREATE TYPE schedule_exception_type AS ENUM ('day_off', 'reduced_hours', 'extra_hours');

-- Метод подсчёта баллов теста
CREATE TYPE scoring_method AS ENUM ('sum', 'average', 'weighted', 'custom');

-- ============================================
-- Migration 002: Users & Auth
-- ============================================

-- Пользователи (центральная таблица)
CREATE TABLE users (
    id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid       UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    full_name  VARCHAR(255) NOT NULL,
    email      VARCHAR(255) NOT NULL UNIQUE,
    phone      VARCHAR(50),
    password_hash VARCHAR(255) NOT NULL,
    avatar_url VARCHAR(500),
    is_active  BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_users_email ON users (email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_active ON users (is_active) WHERE deleted_at IS NULL;

-- Роли
CREATE TABLE roles (
    id          INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    is_system   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Связь пользователя и роли (M:N)
CREATE TABLE user_roles (
    id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id    INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    granted_by INT REFERENCES users(id) ON DELETE SET NULL,
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    UNIQUE (user_id, role_id)
);

-- Разрешения
CREATE TABLE permissions (
    id          INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    module      VARCHAR(50)
);

-- Связь роли и разрешения (M:N)
CREATE TABLE role_permissions (
    id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role_id       INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    UNIQUE (role_id, permission_id)
);

-- Профиль студента (1:1 с users)
CREATE TABLE student_profiles (
    id          INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     INT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    study_group VARCHAR(50),
    study_year  INT,
    faculty     VARCHAR(255),
    birth_date  DATE,
    gender      VARCHAR(20),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Профиль психолога (1:1 с users)
CREATE TABLE psychologist_profiles (
    id               INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id          INT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    specialization   VARCHAR(255),
    bio              TEXT,
    experience_years INT,
    education        TEXT,
    is_accepting     BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Активные сессии (JWT refresh tokens)
CREATE TABLE user_sessions (
    id           VARCHAR(255) PRIMARY KEY,
    user_id      INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ip_address   INET,
    user_agent   TEXT,
    started_at   TIMESTAMPTZ DEFAULT NOW(),
    last_active  TIMESTAMPTZ DEFAULT NOW(),
    expires_at   TIMESTAMPTZ NOT NULL,
    is_revoked   BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_sessions_user ON user_sessions (user_id) WHERE is_revoked = FALSE;
CREATE INDEX idx_sessions_expires ON user_sessions (expires_at) WHERE is_revoked = FALSE;

-- MFA (двухфакторная аутентификация)
CREATE TABLE user_mfa_methods (
    id              INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    method_type     VARCHAR(20) NOT NULL,
    secret_encrypted TEXT,
    recovery_codes  TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    verified_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Политики конфиденциальности (версионируемые)
CREATE TABLE consents (
    id           INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_type  VARCHAR(100) NOT NULL,
    version      INT NOT NULL DEFAULT 1,
    title        VARCHAR(255) NOT NULL,
    content      TEXT NOT NULL,
    is_mandatory BOOLEAN DEFAULT TRUE,
    published_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (policy_type, version)
);

-- Записи согласий пользователей
CREATE TABLE consent_records (
    id          INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     INT NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    consent_id  INT NOT NULL REFERENCES consents(id) ON DELETE RESTRICT,
    accepted    BOOLEAN NOT NULL,
    ip_address  INET,
    user_agent  TEXT,
    accepted_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at  TIMESTAMPTZ
);

CREATE INDEX idx_consent_records_user ON consent_records (user_id, consent_id);

-- Экстренные контакты клиента
CREATE TABLE emergency_contacts (
    id           INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id      INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    contact_name VARCHAR(255) NOT NULL,
    relationship VARCHAR(100),
    phone        VARCHAR(50) NOT NULL,
    email        VARCHAR(255),
    is_primary   BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

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

-- ============================================
-- Migration 004: Content (categories, articles, news, resources, Q&A)
-- ============================================

-- Универсальные категории (с иерархией)
CREATE TABLE categories (
    id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    slug          VARCHAR(100) NOT NULL UNIQUE,
    parent_id     INT REFERENCES categories(id) ON DELETE SET NULL,
    description   TEXT,
    display_order INT DEFAULT 0,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Статьи
CREATE TABLE articles (
    id           INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid         UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    title        VARCHAR(255) NOT NULL,
    slug         VARCHAR(255) UNIQUE,
    excerpt      TEXT,
    content      TEXT,
    cover_image  INT REFERENCES media_files(id) ON DELETE SET NULL,
    created_by   INT REFERENCES users(id) ON DELETE SET NULL,
    is_published BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);

CREATE INDEX idx_articles_published ON articles (published_at DESC) WHERE is_published = TRUE AND deleted_at IS NULL;
CREATE INDEX idx_articles_fulltext ON articles USING gin (to_tsvector('russian', coalesce(title,'') || ' ' || coalesce(content,'')));

-- Связь статей с категориями (M:N)
CREATE TABLE article_categories (
    article_id  INT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    category_id INT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, category_id)
);

-- Новости
CREATE TABLE news (
    id           INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid         UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    title        VARCHAR(255) NOT NULL,
    content      TEXT,
    cover_image  INT REFERENCES media_files(id) ON DELETE SET NULL,
    created_by   INT REFERENCES users(id) ON DELETE SET NULL,
    is_published BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);

CREATE INDEX idx_news_published ON news (published_at DESC) WHERE is_published = TRUE AND deleted_at IS NULL;

-- Ресурсы помощи
CREATE TABLE help_resources (
    id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_id   INT REFERENCES categories(id) ON DELETE SET NULL,
    name          VARCHAR(255) NOT NULL,
    phone         VARCHAR(50),
    address       TEXT,
    website       VARCHAR(255),
    working_hours VARCHAR(255),
    display_order INT DEFAULT 0,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Вопросы и ответы (Q&A)
CREATE TABLE questions_answers (
    id                       INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid                     UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    author_id                INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_psychologist_id INT REFERENCES users(id) ON DELETE SET NULL,
    question_text            TEXT NOT NULL,
    answer_text              TEXT,
    status                   qa_status DEFAULT 'pending',
    visibility               qa_visibility DEFAULT 'private',
    display_name             VARCHAR(255),
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    answered_at              TIMESTAMPTZ,
    updated_at               TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_qa_author ON questions_answers (author_id);
CREATE INDEX idx_qa_psychologist ON questions_answers (assigned_psychologist_id);
CREATE INDEX idx_qa_status ON questions_answers (status) WHERE status IN ('pending', 'assigned');
CREATE INDEX idx_qa_published ON questions_answers (created_at DESC) WHERE status = 'published';

-- ============================================
-- Migration 005: Psychodiagnostics
-- ============================================

-- Тесты
CREATE TABLE tests (
    id             INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid           UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    title          VARCHAR(255) NOT NULL,
    description    TEXT,
    version        INT DEFAULT 1,
    scoring        scoring_method DEFAULT 'sum',
    max_score      INT,
    time_limit_min INT,
    created_by     INT REFERENCES users(id) ON DELETE SET NULL,
    is_active      BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW(),
    deleted_at     TIMESTAMPTZ
);

-- Связь тестов с категориями (M:N)
CREATE TABLE test_categories (
    test_id     INT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    category_id INT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (test_id, category_id)
);

-- Вопросы тестов
CREATE TABLE questions (
    id             INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    test_id        INT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    question_text  TEXT NOT NULL,
    question_order INT NOT NULL,
    question_type  question_type DEFAULT 'single_choice',
    is_required    BOOLEAN DEFAULT TRUE,
    config         JSONB DEFAULT '{}',
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_questions_test ON questions (test_id, question_order);

-- Варианты ответов
CREATE TABLE options (
    id           INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question_id  INT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    option_text  TEXT NOT NULL,
    option_order INT NOT NULL,
    value_score  INT DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_options_question ON options (question_id, option_order);

-- Связь вопросов с медиафайлами (M:N)
CREATE TABLE question_media (
    id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question_id   INT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    media_id      INT NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    media_role    media_role_question DEFAULT 'main',
    display_order INT DEFAULT 1,
    caption       TEXT
);

CREATE INDEX idx_qmedia_question ON question_media (question_id);

-- Связь вариантов ответов с медиафайлами (M:N)
CREATE TABLE option_media (
    id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    option_id     INT NOT NULL REFERENCES options(id) ON DELETE CASCADE,
    media_id      INT NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    media_role    media_role_option DEFAULT 'icon',
    display_order INT DEFAULT 1
);

CREATE INDEX idx_omedia_option ON option_media (option_id);

-- Результаты прохождения тестов
CREATE TABLE test_results (
    id           INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid         UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    user_id      INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    test_id      INT NOT NULL REFERENCES tests(id) ON DELETE RESTRICT,
    test_version INT NOT NULL,
    total_score  INT,
    max_possible INT,
    scoring_used scoring_method,
    recommendations TEXT,
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_results_user ON test_results (user_id);
CREATE INDEX idx_results_test ON test_results (test_id);
CREATE INDEX idx_results_submitted ON test_results (submitted_at DESC);

-- Подшкалы результатов (для HADS, MMPI, BDI и т.д.)
CREATE TABLE test_result_scales (
    id             INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    test_result_id INT NOT NULL REFERENCES test_results(id) ON DELETE CASCADE,
    scale_name     VARCHAR(100) NOT NULL,
    score          INT NOT NULL,
    max_score      INT,
    interpretation TEXT,
    metadata       JSONB DEFAULT '{}'
);

CREATE INDEX idx_scales_result ON test_result_scales (test_result_id);

-- Ответы студентов на вопросы
CREATE TABLE student_answers (
    id               INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    test_result_id   INT NOT NULL REFERENCES test_results(id) ON DELETE CASCADE,
    question_id      INT NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
    option_id        INT REFERENCES options(id) ON DELETE RESTRICT,
    free_text_answer TEXT,
    scale_value      INT,
    selected_options INT[],
    time_spent_sec   INT
);

CREATE INDEX idx_answers_result ON student_answers (test_result_id);
CREATE INDEX idx_answers_question ON student_answers (question_id);

-- ============================================
-- Migration 006: Consultations
-- ============================================

-- Терапевтическое взаимодействие (психолог — клиент)
CREATE TABLE therapy_engagements (
    id              INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid            UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    client_id       INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    psychologist_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          engagement_status DEFAULT 'active',
    primary_concern TEXT,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    transferred_to  INT REFERENCES users(id) ON DELETE SET NULL,
    transfer_reason TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_engagement_different_people CHECK (client_id <> psychologist_id)
);

CREATE INDEX idx_engagements_client ON therapy_engagements (client_id);
CREATE INDEX idx_engagements_psychologist ON therapy_engagements (psychologist_id);
CREATE INDEX idx_engagements_active ON therapy_engagements (psychologist_id, status) WHERE status = 'active';

-- Шаблоны расписания психологов
CREATE TABLE schedule_rules (
    id                    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    psychologist_id       INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day_of_week           INT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time            TIME NOT NULL,
    end_time              TIME NOT NULL,
    slot_duration_minutes INT DEFAULT 50,
    break_minutes         INT DEFAULT 10,
    is_active             BOOLEAN DEFAULT TRUE,
    effective_from        DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_until       DATE,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_schedule_times CHECK (start_time < end_time)
);

CREATE INDEX idx_schedule_psych ON schedule_rules (psychologist_id) WHERE is_active = TRUE;

-- Исключения из расписания (отпуск, больничный, доп. часы)
CREATE TABLE schedule_exceptions (
    id              INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    psychologist_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exception_date  DATE NOT NULL,
    exception_type  schedule_exception_type NOT NULL,
    start_time      TIME,
    end_time        TIME,
    reason          TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (psychologist_id, exception_date)
);

-- Записи на консультации
CREATE TABLE appointments (
    id                  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid                UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    client_id           INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    psychologist_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    engagement_id       INT REFERENCES therapy_engagements(id) ON DELETE SET NULL,
    starts_at           TIMESTAMPTZ NOT NULL,
    duration_minutes    INT NOT NULL DEFAULT 50,
    modality            appointment_modality DEFAULT 'in_person',
    topic               TEXT,
    status              appointment_status DEFAULT 'scheduled',
    cancellation_reason TEXT,
    canceled_by         INT REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ,
    CONSTRAINT chk_appointment_different CHECK (client_id <> psychologist_id)
);

-- EXCLUDE — предотвращение пересечения слотов у одного психолога на уровне БД
ALTER TABLE appointments ADD CONSTRAINT no_overlap_psychologist
    EXCLUDE USING gist (
        psychologist_id WITH =,
        tstzrange(starts_at, starts_at + (duration_minutes || ' minutes')::interval) WITH &&
    ) WHERE (status NOT IN ('canceled', 'no_show') AND deleted_at IS NULL);

CREATE INDEX idx_appointments_client ON appointments (client_id);
CREATE INDEX idx_appointments_psychologist ON appointments (psychologist_id, starts_at);
CREATE INDEX idx_appointments_upcoming ON appointments (starts_at)
    WHERE status IN ('scheduled', 'confirmed') AND deleted_at IS NULL;

-- Заметки сессий (отдельно от appointments)
CREATE TABLE session_notes (
    id                    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid                  UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    appointment_id        INT REFERENCES appointments(id) ON DELETE SET NULL,
    engagement_id         INT REFERENCES therapy_engagements(id) ON DELETE SET NULL,
    author_id             INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    note_type             session_note_type DEFAULT 'general',
    content               TEXT NOT NULL,
    is_shared_with_client BOOLEAN DEFAULT FALSE,
    version               INT DEFAULT 1,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_notes_appointment ON session_notes (appointment_id);
CREATE INDEX idx_notes_engagement ON session_notes (engagement_id);
CREATE INDEX idx_notes_author ON session_notes (author_id);

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

-- ============================================
-- Migration 009: Views & Functions
-- ============================================

-- Активные пользователи с ролями
CREATE OR REPLACE VIEW v_users_with_roles AS
SELECT
    u.id,
    u.uuid,
    u.full_name,
    u.email,
    u.is_active,
    u.last_login,
    u.created_at,
    array_agg(DISTINCT r.name) FILTER (WHERE r.name IS NOT NULL) AS roles
FROM users u
LEFT JOIN user_roles ur ON u.id = ur.user_id AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
LEFT JOIN roles r ON ur.role_id = r.id
WHERE u.deleted_at IS NULL
GROUP BY u.id;

-- Активные клиенты психолога
CREATE OR REPLACE VIEW v_psychologist_clients AS
SELECT
    te.psychologist_id,
    te.client_id,
    u.full_name AS client_name,
    u.email AS client_email,
    te.status AS engagement_status,
    te.started_at,
    te.primary_concern,
    COUNT(a.id) AS total_appointments,
    MAX(a.starts_at) AS last_appointment,
    MIN(a.starts_at) FILTER (WHERE a.starts_at > NOW() AND a.status IN ('scheduled', 'confirmed')) AS next_appointment
FROM therapy_engagements te
JOIN users u ON te.client_id = u.id
LEFT JOIN appointments a ON te.id = a.engagement_id AND a.deleted_at IS NULL
WHERE te.status = 'active'
GROUP BY te.psychologist_id, te.client_id, u.full_name, u.email, te.status, te.started_at, te.primary_concern;

-- Действующие правила расписания психологов
CREATE OR REPLACE VIEW v_schedule_active AS
SELECT
    sr.psychologist_id,
    sr.day_of_week,
    sr.start_time,
    sr.end_time,
    sr.slot_duration_minutes,
    sr.break_minutes,
    sr.effective_from,
    sr.effective_until
FROM schedule_rules sr
WHERE sr.is_active = TRUE
  AND sr.effective_from <= CURRENT_DATE
  AND (sr.effective_until IS NULL OR sr.effective_until >= CURRENT_DATE);

-- Сводка активности пользователя
CREATE OR REPLACE VIEW v_user_activity_summary AS
SELECT
    u.id AS user_id,
    u.full_name,
    u.email,
    COUNT(DISTINCT tr.id) AS tests_completed,
    COUNT(DISTINCT a.id) AS appointments_total,
    COUNT(DISTINCT a.id) FILTER (WHERE a.status = 'completed') AS appointments_completed,
    COUNT(DISTINCT qa.id) AS questions_asked,
    MAX(al.created_at) AS last_activity
FROM users u
LEFT JOIN test_results tr ON u.id = tr.user_id
LEFT JOIN appointments a ON u.id = a.client_id AND a.deleted_at IS NULL
LEFT JOIN questions_answers qa ON u.id = qa.author_id
LEFT JOIN audit_log al ON u.id = al.user_id
WHERE u.deleted_at IS NULL
GROUP BY u.id, u.full_name, u.email;

-- Вопросы тестов с медиафайлами
CREATE OR REPLACE VIEW v_questions_with_media AS
SELECT
    q.id AS question_id,
    q.test_id,
    q.question_text,
    q.question_order,
    q.question_type,
    q.is_required,
    q.config,
    COALESCE(
        json_agg(
            json_build_object(
                'media_id', mf.id,
                'file_name', mf.file_name,
                'file_path', mf.file_path,
                'file_type', mf.file_type,
                'media_role', qm.media_role,
                'caption', qm.caption
            )
        ) FILTER (WHERE mf.id IS NOT NULL),
        '[]'::json
    ) AS media
FROM questions q
LEFT JOIN question_media qm ON q.id = qm.question_id
LEFT JOIN media_files mf ON qm.media_id = mf.id AND mf.deleted_at IS NULL
GROUP BY q.id;

-- -----------------------------------------------
-- Функции
-- -----------------------------------------------

-- Логирование активности (application-level, не триггер)
CREATE OR REPLACE FUNCTION log_activity(
    p_user_id INT,
    p_user_role VARCHAR,
    p_event_type VARCHAR,
    p_entity_type VARCHAR DEFAULT NULL,
    p_entity_id INT DEFAULT NULL,
    p_description TEXT DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}',
    p_ip INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL,
    p_session_id VARCHAR DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
    v_id BIGINT;
BEGIN
    INSERT INTO audit_log (user_id, user_role, event_type, entity_type, entity_id, description, metadata, ip_address, user_agent, session_id)
    VALUES (p_user_id, p_user_role, p_event_type, p_entity_type, p_entity_id, p_description, p_metadata, p_ip, p_user_agent, p_session_id)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- Логирование аутентификации
CREATE OR REPLACE FUNCTION log_auth(
    p_user_id INT,
    p_email VARCHAR,
    p_event auth_event,
    p_success BOOLEAN DEFAULT TRUE,
    p_failure_reason VARCHAR DEFAULT NULL,
    p_ip INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL,
    p_session_id VARCHAR DEFAULT NULL,
    p_mfa_method VARCHAR DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    INSERT INTO auth_log (user_id, user_email, event, success, failure_reason, ip_address, user_agent, session_id, mfa_method)
    VALUES (p_user_id, p_email, p_event, p_success, p_failure_reason, p_ip, p_user_agent, p_session_id, p_mfa_method);
END;
$$ LANGUAGE plpgsql;

-- Логирование изменений данных (вызывается из приложения с явным actor_id)
CREATE OR REPLACE FUNCTION log_data_change(
    p_actor_id INT,
    p_actor_role VARCHAR,
    p_table_name VARCHAR,
    p_record_id INT,
    p_operation VARCHAR,
    p_old_values JSONB DEFAULT NULL,
    p_new_values JSONB DEFAULT NULL,
    p_ip INET DEFAULT NULL
) RETURNS VOID AS $$
DECLARE
    v_changed TEXT[];
BEGIN
    IF p_old_values IS NOT NULL AND p_new_values IS NOT NULL THEN
        SELECT array_agg(key)
        INTO v_changed
        FROM jsonb_each(p_new_values) n
        WHERE NOT EXISTS (
            SELECT 1 FROM jsonb_each(p_old_values) o WHERE o.key = n.key AND o.value = n.value
        );
    END IF;

    INSERT INTO data_change_log (actor_id, actor_role, table_name, record_id, operation, old_values, new_values, changed_fields, ip_address)
    VALUES (p_actor_id, p_actor_role, p_table_name, p_record_id, p_operation, p_old_values, p_new_values, v_changed, p_ip);
END;
$$ LANGUAGE plpgsql;

-- Анонимизация IP-адресов старше N дней (GDPR / 152-ФЗ)
CREATE OR REPLACE FUNCTION anonymize_old_ips(days_old INT DEFAULT 90) RETURNS INT AS $$
DECLARE
    affected INT := 0;
    cnt INT;
BEGIN
    UPDATE audit_log SET ip_address = NULL WHERE created_at < NOW() - (days_old || ' days')::interval AND ip_address IS NOT NULL;
    GET DIAGNOSTICS cnt = ROW_COUNT; affected := affected + cnt;

    UPDATE auth_log SET ip_address = NULL WHERE created_at < NOW() - (days_old || ' days')::interval AND ip_address IS NOT NULL;
    GET DIAGNOSTICS cnt = ROW_COUNT; affected := affected + cnt;

    UPDATE data_change_log SET ip_address = NULL WHERE created_at < NOW() - (days_old || ' days')::interval AND ip_address IS NOT NULL;
    GET DIAGNOSTICS cnt = ROW_COUNT; affected := affected + cnt;

    RETURN affected;
END;
$$ LANGUAGE plpgsql;

-- Автообновление updated_at
CREATE OR REPLACE FUNCTION update_timestamp() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггеры автообновления updated_at
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER trg_student_profiles_updated BEFORE UPDATE ON student_profiles FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER trg_psychologist_profiles_updated BEFORE UPDATE ON psychologist_profiles FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER trg_articles_updated BEFORE UPDATE ON articles FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER trg_news_updated BEFORE UPDATE ON news FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER trg_appointments_updated BEFORE UPDATE ON appointments FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER trg_therapy_engagements_updated BEFORE UPDATE ON therapy_engagements FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER trg_questions_answers_updated BEFORE UPDATE ON questions_answers FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER trg_tests_updated BEFORE UPDATE ON tests FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER trg_help_resources_updated BEFORE UPDATE ON help_resources FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ============================================
-- Migration 010: Seed Data
-- ============================================

-- Роли
INSERT INTO roles (name, display_name, description, is_system) VALUES
    ('student',      'Студент/Клиент',  'Проходит тесты, записывается на консультации', TRUE),
    ('psychologist', 'Психолог',        'Ведут консультации, управляет тестами',        TRUE),
    ('admin',        'Администратор',   'Полный доступ к системе',                     TRUE),
    ('supervisor',   'Супервизор',      'Наблюдает за работой психологов-стажёров',     TRUE);

-- Разрешения
INSERT INTO permissions (code, description, module) VALUES
    ('users.view_own',            'Просмотр своего профиля',              'users'),
    ('users.edit_own',            'Редактирование своего профиля',        'users'),
    ('users.view_all',            'Просмотр всех пользователей',          'users'),
    ('users.manage',              'Управление пользователями',            'users'),
    ('appointments.create',       'Создание записи на консультацию',      'appointments'),
    ('appointments.view_own',     'Просмотр своих консультаций',          'appointments'),
    ('appointments.view_assigned','Просмотр назначенных консультаций',    'appointments'),
    ('appointments.manage',       'Управление всеми консультациями',      'appointments'),
    ('tests.take',                'Прохождение тестов',                   'tests'),
    ('tests.view_own_results',    'Просмотр своих результатов',           'tests'),
    ('tests.view_client_results', 'Просмотр результатов клиентов',       'tests'),
    ('tests.manage',              'Управление тестами (CRUD)',            'tests'),
    ('content.view',              'Просмотр публичного контента',         'content'),
    ('content.manage',            'Управление контентом (статьи, новости)','content'),
    ('qa.ask',                    'Задать вопрос',                        'qa'),
    ('qa.answer',                 'Ответить на вопрос',                   'qa'),
    ('analytics.view',            'Просмотр аналитики',                   'analytics'),
    ('analytics.export',          'Экспорт данных',                       'analytics'),
    ('audit.view',                'Просмотр журнала аудита',              'audit');

-- Привязка разрешений к ролям

-- Студент
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'student' AND p.code IN (
    'users.view_own', 'users.edit_own',
    'appointments.create', 'appointments.view_own',
    'tests.take', 'tests.view_own_results',
    'content.view', 'qa.ask'
);

-- Психолог
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'psychologist' AND p.code IN (
    'users.view_own', 'users.edit_own',
    'appointments.view_assigned', 'appointments.manage',
    'tests.view_client_results', 'tests.manage',
    'content.view', 'content.manage',
    'qa.answer', 'analytics.view'
);

-- Администратор — все разрешения
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'admin';

-- Супервизор
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'supervisor' AND p.code IN (
    'users.view_own', 'users.edit_own', 'users.view_all',
    'appointments.view_assigned',
    'tests.view_client_results',
    'content.view', 'analytics.view', 'audit.view'
);

-- Категории
INSERT INTO categories (name, slug, description, display_order) VALUES
    ('Стресс и тревожность',  'stress',          'Методики диагностики стресса и тревоги',       1),
    ('Депрессия',             'depression',       'Диагностика депрессивных состояний',            2),
    ('ПТСР',                  'ptsd',             'Посттравматическое стрессовое расстройство',    3),
    ('Адаптация',             'adaptation',       'Адаптация первокурсников',                      4),
    ('Саморегуляция',         'self-regulation',  'Методы эмоциональной саморегуляции',            5),
    ('Конфликтология',        'conflicts',        'Разрешение конфликтов',                         6),
    ('Профориентация',        'career',           'Профессиональная ориентация и способности',     7),
    ('Общее самочувствие',    'wellbeing',        'Самопознание и общее самочувствие',             8),
    ('Первая помощь',         'first-aid',        'Первая психологическая помощь',                 9),
    ('Кризисные ситуации',    'crisis',           'Кризисные и экстренные ситуации',              10);

-- Шаблоны уведомлений
INSERT INTO notification_templates (code, title, body, channel) VALUES
    ('appointment_created',  'Новая запись на консультацию', 'Запись на {{date}} в {{time}} создана.',               'web'),
    ('appointment_reminder', 'Напоминание о консультации',   'Напоминаем: консультация {{date}} в {{time}}.',        'email'),
    ('appointment_canceled', 'Консультация отменена',        'Консультация на {{date}} отменена.',                   'web'),
    ('test_result_ready',    'Результаты теста готовы',      'Результаты теста «{{test_title}}» доступны в ЛК.',     'web'),
    ('qa_answered',          'Ответ на ваш вопрос',          'Психолог ответил на ваш вопрос.',                      'web'),
    ('new_qa_assigned',      'Новый вопрос',                 'Вам назначен новый вопрос от клиента.',                'web');

-- Политики конфиденциальности
INSERT INTO consents (policy_type, version, title, content, is_mandatory, published_at) VALUES
    ('privacy_policy',  1, 'Политика конфиденциальности v1',      'Текст политики конфиденциальности...',  TRUE, NOW()),
    ('data_processing', 1, 'Согласие на обработку ПДн v1',        'Текст согласия на обработку ПДн...',    TRUE, NOW()),
    ('test_consent',    1, 'Согласие на прохождение диагностики v1','Текст согласия на диагностику...',    TRUE, NOW());

