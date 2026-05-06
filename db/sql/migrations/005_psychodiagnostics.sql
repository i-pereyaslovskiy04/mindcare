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
