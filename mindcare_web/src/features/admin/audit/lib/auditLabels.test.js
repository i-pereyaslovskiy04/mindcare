import {
  ACTOR_KIND_LABELS,
  AUDIT_EVENT_LABELS,
  AUTH_EVENT_LABELS,
  CHANGED_FIELD_LABELS,
  DETAIL_KEY_LABELS,
  DETAIL_KEY_ORDER,
  ENTITY_TYPE_LABELS,
  EVENT_CATEGORIES,
  EVENT_CATEGORY_LABELS,
  EVENT_CATEGORY_ORDER,
  FAILURE_CODE_LABELS,
  FILTER_KEY_LABELS,
  LEGACY_EVENT_CODE,
  OPERATION_LABELS,
  OUTCOME_LABELS,
  TABLE_LABELS,
  UNKNOWN_LABEL,
  categoryOf,
  changedFieldLabel,
  labelFor,
} from './auditLabels';

/**
 * Ожидаемые множества кодов — снимок живого backend registry (Stage 8):
 * 87 событий audit_log, 7 auth_log, 17 кодов отказа, 23 типа объектов,
 * 4 таблицы data_change_log и 25 пар таблица/поле.
 *
 * Тест держит карты и registry в согласии: новое backend-событие без подписи
 * уронит его, а не утечёт в интерфейс сырым кодом.
 */
const AUDIT_EVENT_CODES = [
  'admin_role_add', 'admin_role_remove', 'admin_role_update',
  'admin_user_activated', 'admin_user_create_failed', 'admin_user_created',
  'admin_user_deactivated', 'admin_user_delete_failed', 'admin_user_deleted',
  'admin_user_update_failed', 'admin_user_updated',
  'appointment_cancel_failed', 'appointment_cancelled',
  'appointment_confirm_failed', 'appointment_confirmed',
  'appointment_create_failed', 'appointment_created',
  'appointment_decline_failed', 'appointment_declined',
  'article_created', 'article_deleted', 'article_updated',
  'audit_logs_viewed',
  'category_created', 'category_deleted', 'category_updated',
  'chat_attachment_downloaded', 'chat_attachment_uploaded',
  'chat_conversation_created', 'chat_message_deleted', 'chat_message_edited',
  'email_domain_add', 'email_domain_disable', 'email_domain_reactivate',
  'email_domain_update',
  'group_session_booking_closed', 'group_session_booking_opened',
  'group_session_cancelled', 'group_session_completed', 'group_session_created',
  'group_session_registered', 'group_session_registration_cancelled',
  'group_session_updated',
  'meeting_type_activated', 'meeting_type_created', 'meeting_type_deactivated',
  'meeting_type_updated',
  'news_created', 'news_deleted', 'news_updated',
  'profile_update_failed', 'profile_updated',
  'schedule_auto_extended', 'schedule_break_created',
  'schedule_break_deactivated', 'schedule_created', 'schedule_deactivated',
  'schedule_exception_created', 'schedule_extended', 'schedule_restored',
  'schedule_rule_created', 'schedule_rule_deactivated', 'schedule_updated',
  'session_note_content_read', 'session_note_created', 'session_note_updated',
  'supervisor_assign_psychologist', 'supervisor_close_engagement',
  'supervisor_create_student', 'supervisor_reactivate_psychologist',
  'supervisor_transfer_psychologist',
  'system_conversation_created',
  'tag_created', 'tag_deleted', 'tag_updated',
  'test_consent_accepted', 'test_created', 'test_deleted', 'test_duplicated',
  'test_submitted', 'test_updated',
  'unregistered_student_card_archived',
  'unregistered_student_card_create_failed',
  'unregistered_student_card_created', 'unregistered_student_card_linked',
  'unregistered_student_card_updated',
  'user_reactivated',
];

const AUTH_EVENT_CODES = [
  'failed_login', 'login', 'logout', 'password_change', 'password_reset',
  'registration_failed', 'registration_succeeded',
];

const FAILURE_CODES = [
  'access_denied', 'account_inactive', 'consent_required', 'domain_not_allowed',
  'email_already_exists', 'engagement_required', 'internal_error',
  'invalid_credentials', 'invalid_request', 'legal_basis_required',
  'no_active_roles', 'otp_expired', 'otp_invalid', 'password_policy',
  'role_policy_violation', 'self_admin_protected', 'user_not_found',
];

const ENTITY_TYPES = [
  'allowed_email_domain', 'appointment', 'article', 'category',
  'chat_attachment', 'chat_conversation', 'chat_message', 'consent_record',
  'group_session', 'group_session_registration', 'meeting_type', 'news',
  'schedule_break', 'schedule_exception', 'schedule_rule', 'schedule_series',
  'session_note', 'tag', 'test', 'test_result', 'therapy_engagement',
  'unregistered_student_card', 'user',
];

const CHANGE_PAIRS = [
  ['group_sessions', 'capacity'], ['group_sessions', 'description'],
  ['group_sessions', 'ends_at'], ['group_sessions', 'format'],
  ['group_sessions', 'meeting_type_id'], ['group_sessions', 'psychologist_id'],
  ['group_sessions', 'starts_at'], ['group_sessions', 'title'],
  ['meeting_types', 'allow_in_person'], ['meeting_types', 'allow_online'],
  ['meeting_types', 'buffer_minutes'], ['meeting_types', 'description'],
  ['meeting_types', 'display_order'], ['meeting_types', 'duration_minutes'],
  ['meeting_types', 'is_bookable'], ['meeting_types', 'is_group'],
  ['meeting_types', 'name'],
  ['unregistered_student_cards', 'birth_date'],
  ['unregistered_student_cards', 'comment'],
  ['unregistered_student_cards', 'email'],
  ['unregistered_student_cards', 'full_name'],
  ['unregistered_student_cards', 'phone'],
  ['unregistered_student_cards', 'primary_concern'],
  ['users', 'full_name'], ['users', 'phone'],
];

describe('полнота карт относительно registry', () => {
  test('87 событий audit_log имеют подпись', () => {
    expect(AUDIT_EVENT_CODES).toHaveLength(87);
    expect(Object.keys(AUDIT_EVENT_LABELS).sort()).toEqual([...AUDIT_EVENT_CODES].sort());
    AUDIT_EVENT_CODES.forEach((code) => {
      expect(labelFor(AUDIT_EVENT_LABELS, code)).not.toBe(UNKNOWN_LABEL);
    });
  });

  test('7 событий auth_log имеют подпись', () => {
    expect(AUTH_EVENT_CODES).toHaveLength(7);
    expect(Object.keys(AUTH_EVENT_LABELS).sort()).toEqual([...AUTH_EVENT_CODES].sort());
  });

  test('17 кодов отказа имеют подпись', () => {
    expect(Object.keys(FAILURE_CODE_LABELS).sort()).toEqual([...FAILURE_CODES].sort());
  });

  test('23 типа объектов имеют подпись', () => {
    expect(Object.keys(ENTITY_TYPE_LABELS).sort()).toEqual([...ENTITY_TYPES].sort());
  });

  test('4 таблицы и операции имеют подпись', () => {
    expect(Object.keys(TABLE_LABELS).sort()).toEqual([
      'group_sessions', 'meeting_types', 'unregistered_student_cards', 'users',
    ]);
    expect(Object.keys(OPERATION_LABELS).sort()).toEqual(['DELETE', 'INSERT', 'UPDATE']);
  });

  test('каждый из 94 кодов отнесён к существующей категории', () => {
    const all = [...AUDIT_EVENT_CODES, ...AUTH_EVENT_CODES];
    expect(all).toHaveLength(94);
    expect(Object.keys(EVENT_CATEGORIES).sort()).toEqual([...all].sort());
    all.forEach((code) => {
      const category = categoryOf(code);
      expect(EVENT_CATEGORY_ORDER).toContain(category);
      expect(EVENT_CATEGORY_LABELS[category]).toBeTruthy();
    });
  });

  test('actor_kind, outcome и filter_keys покрыты', () => {
    expect(Object.keys(ACTOR_KIND_LABELS).sort()).toEqual([
      'anonymous', 'system', 'unavailable', 'user',
    ]);
    expect(Object.keys(OUTCOME_LABELS).sort()).toEqual(['failure', 'success']);
    expect(Object.keys(FILTER_KEY_LABELS)).toHaveLength(13);
  });

  test('все допустимые ключи details имеют подпись и порядок вывода', () => {
    expect(DETAIL_KEY_ORDER.sort()).toEqual(Object.keys(DETAIL_KEY_LABELS).sort());
  });
});

describe('подписи полей data_change_log', () => {
  test('все 25 пар таблица/поле имеют подпись', () => {
    expect(CHANGE_PAIRS).toHaveLength(25);
    CHANGE_PAIRS.forEach(([table, field]) => {
      expect(CHANGED_FIELD_LABELS[table]).toHaveProperty(field);
      expect(changedFieldLabel(table, field)).toBeTruthy();
    });
  });

  test('уникальных имён полей 22 — карта обязана быть вложенной', () => {
    const names = new Set(CHANGE_PAIRS.map(([, field]) => field));
    expect(names.size).toBe(22);
  });

  test('одноимённые поля разных таблиц не подменяют друг друга', () => {
    expect(changedFieldLabel('users', 'full_name'))
      .not.toBe(changedFieldLabel('unregistered_student_cards', 'full_name'));
    expect(changedFieldLabel('users', 'phone'))
      .not.toBe(changedFieldLabel('unregistered_student_cards', 'phone'));
    expect(changedFieldLabel('group_sessions', 'description'))
      .not.toBe(changedFieldLabel('meeting_types', 'description'));
  });

  test('неизвестная пара возвращает само имя поля, а не чужую подпись', () => {
    expect(changedFieldLabel('users', 'unknown_field')).toBe('unknown_field');
    expect(changedFieldLabel('unknown_table', 'full_name')).toBe('full_name');
  });
});

describe('fallback для неизвестных кодов', () => {
  test('legacy_unknown_event получает нейтральную подпись', () => {
    expect(labelFor(AUDIT_EVENT_LABELS, LEGACY_EVENT_CODE)).toBe(UNKNOWN_LABEL);
  });

  test('будущий backend-код не показывается сырым и не «расчёсывается»', () => {
    const future = 'some_future_backend_event';
    const label = labelFor(AUDIT_EVENT_LABELS, future);
    expect(label).toBe(UNKNOWN_LABEL);
    expect(label).not.toContain('some future backend event');
    expect(label).not.toContain(future);
  });

  test('пустые и не-строковые значения безопасны', () => {
    expect(labelFor(AUDIT_EVENT_LABELS, '')).toBe(UNKNOWN_LABEL);
    expect(labelFor(AUDIT_EVENT_LABELS, null)).toBe(UNKNOWN_LABEL);
    expect(labelFor(AUDIT_EVENT_LABELS, undefined)).toBe(UNKNOWN_LABEL);
    expect(labelFor(AUDIT_EVENT_LABELS, 42)).toBe(UNKNOWN_LABEL);
  });

  test('унаследованные свойства Object не считаются подписью', () => {
    expect(labelFor(AUDIT_EVENT_LABELS, 'toString')).toBe(UNKNOWN_LABEL);
    expect(labelFor(AUDIT_EVENT_LABELS, 'constructor')).toBe(UNKNOWN_LABEL);
  });

  test('неизвестный код категории не получает', () => {
    expect(categoryOf('some_future_backend_event')).toBeNull();
  });

  test('явный fallback перекрывает значение по умолчанию', () => {
    expect(labelFor(TABLE_LABELS, 'future_table', 'future_table')).toBe('future_table');
  });
});

describe('устойчивость к длинным подписям', () => {
  test('самая длинная подпись остаётся однострочной строкой без разметки', () => {
    const longest = Object.values(AUDIT_EVENT_LABELS)
      .reduce((a, b) => (b.length > a.length ? b : a));
    expect(typeof longest).toBe('string');
    expect(longest).not.toContain('\n');
    expect(longest).not.toContain('<');
  });
});
