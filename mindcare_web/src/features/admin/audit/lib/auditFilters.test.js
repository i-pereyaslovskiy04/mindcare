import {
  FALLBACK_LIMITS,
  MAX_RECORD_REF,
  SOURCES,
  SOURCE_DEFAULTS,
  buildQuery,
  computePagination,
  defaultBySource,
  defaultCommon,
  isEntityRefAllowed,
  isRecordRefAllowed,
  parseRecordRef,
  pruneEventForCategory,
  routeFilterPatch,
  validateWindow,
} from './auditFilters';

const OPTIONS = {
  actor_kinds: {
    audit_log: ['user', 'system', 'unavailable'],
    auth_log: ['user', 'anonymous', 'unavailable'],
    data_change_log: ['user', 'unavailable'],
  },
};

describe('лимиты по умолчанию', () => {
  test('совпадают с текущим backend-контрактом', () => {
    expect(FALLBACK_LIMITS).toEqual({
      default_range_days: 7,
      max_range_days: 90,
      default_page_size: 20,
      max_page_size: 100,
      max_result_window: 100000,
      orders: ['asc', 'desc'],
    });
  });

  test('окно по умолчанию — семь календарных дней включая сегодня', () => {
    const common = defaultCommon(7);
    expect(common.order).toBe('desc');
    expect(common.actorUuid).toBe('');
    expect(validateWindow(common.dateFrom, common.dateTo, 90)).toBeNull();
  });
});

describe('маршрутизация setFilters по срезам журналов', () => {
  test('общие ключи попадают в общий срез', () => {
    const routed = routeFilterPatch({ dateFrom: '2026-08-01', order: 'asc' }, 'audit_log');
    expect(routed.common).toEqual({ dateFrom: '2026-08-01', order: 'asc' });
    expect(routed.slice).toEqual({});
    expect(routed.ignored).toEqual([]);
  });

  test('ключи журнала попадают в его срез', () => {
    const routed = routeFilterPatch({ eventType: 'login', outcome: 'success' }, 'audit_log');
    expect(routed.slice).toEqual({ eventType: 'login', outcome: 'success' });
  });

  test('ключ чужого журнала отбрасывается', () => {
    // `event` есть у auth_log, `tableName` — у data_change_log.
    const routed = routeFilterPatch({ event: 'login', tableName: 'users' }, 'audit_log');
    expect(routed.slice).toEqual({});
    expect(routed.ignored.sort()).toEqual(['event', 'tableName']);
  });

  test('произвольный ключ отбрасывается', () => {
    const routed = routeFilterPatch({ junk: 1 }, 'auth_log');
    expect(routed.ignored).toEqual(['junk']);
  });

  test('у каждого журнала свой набор дефолтов', () => {
    expect(SOURCES).toEqual(['audit_log', 'auth_log', 'data_change_log']);
    // auth_log роль актора не хранит — ключа actorRole у него нет.
    expect(SOURCE_DEFAULTS.auth_log).not.toHaveProperty('actorRole');
    expect(SOURCE_DEFAULTS.audit_log).toHaveProperty('actorRole');
    expect(defaultBySource().audit_log).toEqual(SOURCE_DEFAULTS.audit_log);
  });
});

describe('категория и событие', () => {
  test('событие своей категории сохраняется', () => {
    expect(pruneEventForCategory('admin_role_add', 'users_roles')).toBe('admin_role_add');
  });

  test('событие чужой категории обнуляется', () => {
    expect(pruneEventForCategory('admin_role_add', 'content')).toBe('');
  });

  test('пустая категория ничего не обнуляет', () => {
    expect(pruneEventForCategory('admin_role_add', '')).toBe('admin_role_add');
  });

  test('пустое событие остаётся пустым', () => {
    expect(pruneEventForCategory('', 'content')).toBe('');
  });
});

describe('точный идентификатор цели', () => {
  test('пустое значение — «не задано», а не ошибка', () => {
    expect(parseRecordRef('')).toEqual({ value: null, error: null });
    expect(parseRecordRef(null)).toEqual({ value: null, error: null });
  });

  test('целое в допустимом диапазоне', () => {
    expect(parseRecordRef('42')).toEqual({ value: 42, error: null });
    expect(parseRecordRef(String(MAX_RECORD_REF)).value).toBe(MAX_RECORD_REF);
  });

  test('нецелое отвергается', () => {
    expect(parseRecordRef('4.2').error).toBeTruthy();
    expect(parseRecordRef('-5').error).toBeTruthy();
    expect(parseRecordRef('abc').error).toBeTruthy();
    expect(parseRecordRef('1e3').error).toBeTruthy();
  });

  test('выход за диапазон INTEGER отвергается', () => {
    expect(parseRecordRef('0').error).toBeTruthy();
    expect(parseRecordRef(String(MAX_RECORD_REF + 1)).error).toBeTruthy();
  });

  test('идентификатор доступен только с не-пользовательским типом цели', () => {
    expect(isEntityRefAllowed('')).toBe(false);
    expect(isEntityRefAllowed('user')).toBe(false);
    expect(isEntityRefAllowed('appointment')).toBe(true);

    expect(isRecordRefAllowed('')).toBe(false);
    expect(isRecordRefAllowed('users')).toBe(false);
    expect(isRecordRefAllowed('meeting_types')).toBe(true);
  });
});

describe('валидация окна', () => {
  test('корректный период проходит', () => {
    expect(validateWindow('2026-08-16', '2026-08-22', 90)).toBeNull();
  });

  test('одна дата — ошибка', () => {
    expect(validateWindow('2026-08-16', '', 90)).toBeTruthy();
    expect(validateWindow('', '2026-08-22', 90)).toBeTruthy();
  });

  test('перевёрнутый диапазон — ошибка', () => {
    expect(validateWindow('2026-08-22', '2026-08-16', 90)).toBeTruthy();
  });

  test('ровно 90 дней проходит, 91 — нет', () => {
    expect(validateWindow('2026-05-25', '2026-08-22', 90)).toBeNull();
    expect(validateWindow('2026-05-24', '2026-08-22', 90)).toBeTruthy();
  });
});

describe('пагинация с поправкой на окно выборки', () => {
  test('обычный случай — ceil(total / size)', () => {
    expect(computePagination(95, 20, 100000)).toEqual({
      totalPages: 5, windowLimited: false,
    });
  });

  test('total больше окна выборки — страница ограничена', () => {
    // ceil(250000/20) = 12500, но backend примет максимум страницу 5000.
    expect(computePagination(250000, 20, 100000)).toEqual({
      totalPages: 5000, windowLimited: true,
    });
  });

  test('ровно на границе окна ограничения нет', () => {
    expect(computePagination(100000, 20, 100000)).toEqual({
      totalPages: 5000, windowLimited: false,
    });
  });

  test('пустая выдача даёт одну страницу', () => {
    expect(computePagination(0, 20, 100000).totalPages).toBe(1);
  });
});

describe('buildQuery', () => {
  const common = {
    dateFrom: '2026-08-16', dateTo: '2026-08-22', order: 'desc', actorUuid: 'u-1',
  };

  test('audit_log отдаёт свои ключи и не отдаёт category', () => {
    const query = buildQuery({
      source: 'audit_log',
      common,
      slice: {
        ...SOURCE_DEFAULTS.audit_log,
        actorKind: 'system',
        category: 'users_roles',
        eventType: 'admin_role_add',
        entityType: 'appointment',
        entityId: '15',
        includeAccessEvents: true,
      },
      page: 2,
      size: 20,
      options: OPTIONS,
    });

    expect(query).toMatchObject({
      page: 2,
      size: 20,
      date_from: '2026-08-16',
      date_to: '2026-08-22',
      order: 'desc',
      actor_uuid: 'u-1',
      actor_kind: 'system',
      event_type: 'admin_role_add',
      entity_type: 'appointment',
      entity_id: 15,
      include_access_events: true,
    });
    expect(query).not.toHaveProperty('category');
  });

  test('идентификатор без разрешённого типа цели не уходит', () => {
    const query = buildQuery({
      source: 'audit_log',
      common,
      slice: { ...SOURCE_DEFAULTS.audit_log, entityType: 'user', entityId: '15' },
      page: 1, size: 20, options: OPTIONS,
    });
    expect(query.entity_id).toBeNull();
  });

  test('невалидный идентификатор не уходит', () => {
    const query = buildQuery({
      source: 'data_change_log',
      common,
      slice: { ...SOURCE_DEFAULTS.data_change_log, tableName: 'meeting_types', recordId: '0' },
      page: 1, size: 20, options: OPTIONS,
    });
    expect(query.record_id).toBeNull();
  });

  test('actor_kind, недостижимый для журнала, отбрасывается', () => {
    // `system` существует для audit_log и не существует для двух других.
    const auth = buildQuery({
      source: 'auth_log',
      common,
      slice: { ...SOURCE_DEFAULTS.auth_log, actorKind: 'system' },
      page: 1, size: 20, options: OPTIONS,
    });
    expect(auth.actor_kind).toBe('');

    const dcl = buildQuery({
      source: 'data_change_log',
      common,
      slice: { ...SOURCE_DEFAULTS.data_change_log, actorKind: 'system' },
      page: 1, size: 20, options: OPTIONS,
    });
    expect(dcl.actor_kind).toBe('');
  });

  test('без справочника actor_kind не отправляется вовсе', () => {
    const query = buildQuery({
      source: 'audit_log',
      common,
      slice: { ...SOURCE_DEFAULTS.audit_log, actorKind: 'system' },
      page: 1, size: 20, options: null,
    });
    expect(query.actor_kind).toBe('');
  });

  test('auth_log сохраняет success=false', () => {
    const query = buildQuery({
      source: 'auth_log',
      common,
      slice: { ...SOURCE_DEFAULTS.auth_log, success: false },
      page: 1, size: 20, options: OPTIONS,
    });
    expect(query.success).toBe(false);
    expect(query).not.toHaveProperty('actor_role');
  });
});
