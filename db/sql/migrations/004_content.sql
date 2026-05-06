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
