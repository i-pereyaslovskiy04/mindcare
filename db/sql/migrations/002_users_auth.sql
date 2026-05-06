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
