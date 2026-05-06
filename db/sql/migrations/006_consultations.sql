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
