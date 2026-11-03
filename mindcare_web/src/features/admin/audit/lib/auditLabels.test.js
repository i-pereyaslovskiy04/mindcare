import {
  ACTOR_KIND_LABELS,
  AUDIT_EVENT_LABELS,
  AUTH_EVENT_LABELS,
  AUTH_METHOD_LABELS,
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
import registrySnapshot from './auditRegistry.snapshot.json';

/**
 * Ожидаемые множества кодов — снимок backend registry, который пишет
 * `mindcare_api/scripts/export_audit_registry.py`; backend-тест
 * `test_audit_registry_snapshot.py` требует, чтобы снимок совпадал с
 * REGISTRY / CHANGE_REGISTRY.
 *
 * Цепочка держит карты и registry в согласии: новое backend-событие без
 * обновления снимка роняет backend-тест, а запись снимка без подписи — этот.
 */
const AUDIT_EVENT_CODES = registrySnapshot.audit_events;
const AUTH_EVENT_CODES = registrySnapshot.auth_events;
const FAILURE_CODES = registrySnapshot.failure_codes;
const ENTITY_TYPES = registrySnapshot.entity_types;
const CHANGE_PAIRS = registrySnapshot.change_pairs;

describe('полнота карт относительно registry', () => {
  test('снимок registry непустой (защита от пустого файла)', () => {
    expect(AUDIT_EVENT_CODES.length).toBeGreaterThan(100);
    expect(AUTH_EVENT_CODES.length).toBeGreaterThan(0);
    expect(FAILURE_CODES.length).toBeGreaterThan(0);
    expect(ENTITY_TYPES.length).toBeGreaterThan(0);
    expect(CHANGE_PAIRS.length).toBeGreaterThan(0);
  });

  test('каждое событие audit_log из снимка имеет подпись, лишних нет', () => {
    expect(Object.keys(AUDIT_EVENT_LABELS).sort()).toEqual([...AUDIT_EVENT_CODES].sort());
    AUDIT_EVENT_CODES.forEach((code) => {
      expect(labelFor(AUDIT_EVENT_LABELS, code)).not.toBe(UNKNOWN_LABEL);
    });
  });

  test('каждое событие auth_log из снимка имеет подпись, лишних нет', () => {
    expect(Object.keys(AUTH_EVENT_LABELS).sort()).toEqual([...AUTH_EVENT_CODES].sort());
  });

  test('каждый код отказа из снимка имеет подпись, лишних нет', () => {
    expect(Object.keys(FAILURE_CODE_LABELS).sort()).toEqual([...FAILURE_CODES].sort());
  });

  test('способы входа auth_log имеют подпись', () => {
    expect(AUTH_METHOD_LABELS).toEqual({
      password: 'Пароль', yandex: 'Яндекс ID', vk: 'VK ID',
    });
    expect(labelFor(AUTH_METHOD_LABELS, 'telegram')).toBe(UNKNOWN_LABEL);
  });

  test('каждый тип объекта из снимка имеет подпись, лишних нет', () => {
    expect(Object.keys(ENTITY_TYPE_LABELS).sort()).toEqual([...ENTITY_TYPES].sort());
  });

  test('4 таблицы и операции имеют подпись', () => {
    expect(Object.keys(TABLE_LABELS).sort()).toEqual(
      [...new Set(CHANGE_PAIRS.map(([table]) => table))].sort(),
    );
    expect(Object.keys(OPERATION_LABELS).sort()).toEqual(['DELETE', 'INSERT', 'UPDATE']);
  });

  test('каждый код снимка отнесён к существующей категории, лишних нет', () => {
    const all = [...AUDIT_EVENT_CODES, ...AUTH_EVENT_CODES];
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
    expect(Object.keys(FILTER_KEY_LABELS)).toHaveLength(14);
    expect(FILTER_KEY_LABELS.auth_method).toBe('способ входа');
  });

  test('все допустимые ключи details имеют подпись и порядок вывода', () => {
    expect(DETAIL_KEY_ORDER.sort()).toEqual(Object.keys(DETAIL_KEY_LABELS).sort());
  });
});

describe('подписи полей data_change_log', () => {
  test('каждая пара таблица/поле из снимка имеет подпись', () => {
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
