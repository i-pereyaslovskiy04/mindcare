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
