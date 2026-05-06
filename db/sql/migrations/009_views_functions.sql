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
