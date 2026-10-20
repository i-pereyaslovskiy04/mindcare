import { act, renderHook, waitFor } from '@testing-library/react';
import { useAdminAuditLogs } from './useAdminAuditLogs';
import {
  getAuditEvents, getAuthEvents, getDataChanges,
} from '../../../../api/audit.api';
import { FALLBACK_LIMITS } from '../lib/auditFilters';

jest.mock('../../../../api/audit.api', () => {
  const getAuditEventsMock = jest.fn();
  const getAuthEventsMock = jest.fn();
  const getDataChangesMock = jest.fn();
  return {
    getAuditEvents: getAuditEventsMock,
    getAuthEvents: getAuthEventsMock,
    getDataChanges: getDataChangesMock,
    AUDIT_LOADERS: {
      audit_log: getAuditEventsMock,
      auth_log: getAuthEventsMock,
      data_change_log: getDataChangesMock,
    },
  };
});

const OPTIONS = {
  actor_kinds: {
    audit_log: ['user', 'system', 'unavailable'],
    auth_log: ['user', 'anonymous', 'unavailable'],
    data_change_log: ['user', 'unavailable'],
  },
  limits: FALLBACK_LIMITS,
};

const emptyPage = (overrides = {}) => ({
  items: [], total: 0, page: 1, size: 20, ...overrides,
});

beforeEach(() => {
  jest.clearAllMocks();
  getAuditEvents.mockResolvedValue(emptyPage({ items: [{ entry_id: '1' }], total: 1 }));
  getAuthEvents.mockResolvedValue(emptyPage({ items: [{ entry_id: '2' }], total: 2 }));
  getDataChanges.mockResolvedValue(emptyPage({ items: [{ entry_id: '3' }], total: 3 }));
});

function setup(props = {}) {
  return renderHook(() =>
    useAdminAuditLogs({ options: OPTIONS, limits: OPTIONS.limits, ...props }));
}

async function ready(result) {
  await waitFor(() => expect(result.current.loading).toBe(false));
}

const lastCall = (fn) => fn.mock.calls[fn.mock.calls.length - 1][0];

describe('первая загрузка', () => {
  test('журнал по умолчанию — audit_log, страница 1, размер из limits', async () => {
    const { result } = setup();
    await ready(result);

    expect(getAuditEvents).toHaveBeenCalledTimes(1);
    expect(getAuthEvents).not.toHaveBeenCalled();
    expect(getDataChanges).not.toHaveBeenCalled();

    expect(result.current.source).toBe('audit_log');
    expect(result.current.page).toBe(1);
    expect(result.current.size).toBe(20);
    expect(result.current.items).toHaveLength(1);
    expect(result.current.total).toBe(1);
    expect(result.current.error).toBeNull();
  });

  test('окно по умолчанию — 7 календарных дней, отправляется явными датами', async () => {
    const { result } = setup();
    await ready(result);

    const query = lastCall(getAuditEvents);
    expect(query.date_from).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(query.date_to).toMatch(/^\d{4}-\d{2}-\d{2}$/);

    const days = (Date.parse(query.date_to) - Date.parse(query.date_from)) / 86400000 + 1;
    expect(days).toBe(7);
    expect(query.order).toBe('desc');
  });

  test('query существует ради контракта, но никуда не отправляется', async () => {
    const { result } = setup();
    await ready(result);

    await act(async () => { result.current.setQuery('Тестовый Пользователь'); });
    await ready(result);

    expect(result.current.query).toBe('Тестовый Пользователь');
    const serialized = JSON.stringify(getAuditEvents.mock.calls);
    expect(serialized).not.toContain('Тестовый');
  });
});

describe('переключение журналов', () => {
  test('каждая вкладка бьёт только в свой endpoint', async () => {
    const { result } = setup();
    await ready(result);

    await act(async () => { result.current.setSource('auth_log'); });
    await ready(result);
    expect(getAuthEvents).toHaveBeenCalledTimes(1);
    expect(result.current.total).toBe(2);

    await act(async () => { result.current.setSource('data_change_log'); });
    await ready(result);
    expect(getDataChanges).toHaveBeenCalledTimes(1);
    expect(result.current.total).toBe(3);

    expect(getAuditEvents).toHaveBeenCalledTimes(1);
  });

  test('строки предыдущего журнала не остаются на экране', async () => {
    let resolveAuth;
    getAuthEvents.mockImplementationOnce(
      () => new Promise((resolve) => { resolveAuth = resolve; }),
    );

    const { result } = setup();
    await ready(result);
    expect(result.current.items).toHaveLength(1);

    await act(async () => { result.current.setSource('auth_log'); });
    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);

    await act(async () => {
      resolveAuth(emptyPage({ items: [{ entry_id: '2' }], total: 2 }));
      await Promise.resolve();
    });
  });

  test('повторный выбор той же вкладки не перезапрашивает', async () => {
    const { result } = setup();
    await ready(result);

    await act(async () => { result.current.setSource('audit_log'); });
    await ready(result);

    expect(getAuditEvents).toHaveBeenCalledTimes(1);
  });

  test('НЕДОПУСТИМЫЙ actor_kind не уезжает на другую вкладку', async () => {
    const { result } = setup();
    await ready(result);

    // `system` достижим только для audit_log.
    await act(async () => { result.current.setFilters({ actorKind: 'system' }); });
    await ready(result);
    expect(lastCall(getAuditEvents).actor_kind).toBe('system');

    await act(async () => { result.current.setSource('auth_log'); });
    await ready(result);
    expect(lastCall(getAuthEvents).actor_kind).toBe('');

    await act(async () => { result.current.setSource('data_change_log'); });
    await ready(result);
    expect(lastCall(getDataChanges).actor_kind).toBe('');
  });

  test('фильтры своего журнала переживают переключение туда-обратно', async () => {
    const { result } = setup();
    await ready(result);

    await act(async () => { result.current.setFilters({ eventType: 'admin_role_add' }); });
    await ready(result);

    await act(async () => { result.current.setSource('auth_log'); });
    await ready(result);
    await act(async () => { result.current.setFilters({ event: 'failed_login' }); });
    await ready(result);

    await act(async () => { result.current.setSource('audit_log'); });
    await ready(result);

    expect(result.current.filters.eventType).toBe('admin_role_add');
    expect(lastCall(getAuditEvents).event_type).toBe('admin_role_add');
    // Ключ чужого журнала в текущем срезе не появился.
    expect(result.current.filters.event).toBeUndefined();
  });
});

describe('фильтры', () => {
  test('чужой ключ игнорируется и не ломает состояние', async () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
    const { result } = setup();
    await ready(result);

    await act(async () => { result.current.setFilters({ tableName: 'users' }); });
    await ready(result);

    expect(result.current.filters.tableName).toBeUndefined();
    expect(lastCall(getAuditEvents)).not.toHaveProperty('table_name');
    warn.mockRestore();
  });

  test('смена категории обнуляет несовместимое событие', async () => {
    const { result } = setup();
    await ready(result);

    await act(async () => { result.current.setFilters({ eventType: 'admin_role_add' }); });
    await ready(result);
    expect(result.current.filters.eventType).toBe('admin_role_add');

    await act(async () => { result.current.setFilters({ category: 'content' }); });
    await ready(result);
    expect(result.current.filters.eventType).toBe('');
    expect(lastCall(getAuditEvents).event_type).toBe('');
  });

  test('смена категории сохраняет событие своей категории', async () => {
    const { result } = setup();
    await ready(result);

    await act(async () => { result.current.setFilters({ eventType: 'admin_role_add' }); });
    await act(async () => { result.current.setFilters({ category: 'users_roles' }); });
    await ready(result);

    expect(result.current.filters.eventType).toBe('admin_role_add');
  });

  test('смена типа объекта обнуляет идентификатор', async () => {
    const { result } = setup();
    await ready(result);

    await act(async () => {
      result.current.setFilters({ entityType: 'appointment', entityId: '12' });
    });
    await ready(result);
    expect(lastCall(getAuditEvents).entity_id).toBe(12);

    await act(async () => { result.current.setFilters({ entityType: 'article' }); });
    await ready(result);
    expect(result.current.filters.entityId).toBe('');
    expect(lastCall(getAuditEvents).entity_id).toBeNull();
  });

  test('смена таблицы обнуляет идентификатор записи', async () => {
    const { result } = setup();
    await ready(result);
    await act(async () => { result.current.setSource('data_change_log'); });
    await ready(result);

    await act(async () => {
      result.current.setFilters({ tableName: 'meeting_types', recordId: '9' });
    });
    await ready(result);
    expect(lastCall(getDataChanges).record_id).toBe(9);

    await act(async () => { result.current.setFilters({ tableName: 'group_sessions' }); });
    await ready(result);
    expect(result.current.filters.recordId).toBe('');
  });

  test('любой фильтр сбрасывает страницу на первую', async () => {
    const { result } = setup();
    await ready(result);

    await act(async () => { result.current.setPage(3); });
    await ready(result);
    expect(result.current.page).toBe(3);

    await act(async () => { result.current.setFilters({ outcome: 'failure' }); });
    await ready(result);
    expect(result.current.page).toBe(1);
    expect(lastCall(getAuditEvents).page).toBe(1);
  });

  test('смена дат и порядка тоже сбрасывает страницу', async () => {
    const { result } = setup();
    await ready(result);

    await act(async () => { result.current.setPage(2); });
    await ready(result);
    await act(async () => { result.current.setFilters({ order: 'asc' }); });
    await ready(result);

    expect(result.current.page).toBe(1);
    expect(lastCall(getAuditEvents).order).toBe('asc');
  });
});

describe('участник', () => {
  const ACTOR = {
    uuid: '11111111-1111-4111-8111-111111111111',
    fullName: 'Тестовый Пользователь',
    emailMasked: 't***@example.test',
    isDeleted: false,
  };

  test('selectActor одним изменением ставит подпись и actor_uuid', async () => {
    const { result } = setup();
    await ready(result);

    await act(async () => { result.current.selectActor(ACTOR); });
    await ready(result);

    expect(result.current.selectedActor).toEqual(ACTOR);
    expect(result.current.filters.actorUuid).toBe(ACTOR.uuid);
    expect(lastCall(getAuditEvents).actor_uuid).toBe(ACTOR.uuid);
    expect(result.current.page).toBe(1);
  });

  test('в запрос уходит только UUID, без ФИО и email', async () => {
    const { result } = setup();
    await ready(result);
    await act(async () => { result.current.selectActor(ACTOR); });
    await ready(result);

    const serialized = JSON.stringify(getAuditEvents.mock.calls);
    expect(serialized).not.toContain('Тестовый');
    expect(serialized).not.toContain('example.test');
  });

  test('clearActor убирает и подпись, и uuid, и меняет actorResetKey', async () => {
    const { result } = setup();
    await ready(result);
    await act(async () => { result.current.selectActor(ACTOR); });
    await ready(result);

    const keyBefore = result.current.actorResetKey;
    await act(async () => { result.current.clearActor(); });
    await ready(result);

    expect(result.current.selectedActor).toBeNull();
    expect(result.current.filters.actorUuid).toBe('');
    expect(lastCall(getAuditEvents).actor_uuid).toBe('');
    expect(result.current.actorResetKey).toBeGreaterThan(keyBefore);
  });

  test('setFilters({actorUuid: ""}) синхронно обнуляет и выбранного участника', async () => {
    const { result } = setup();
    await ready(result);
    await act(async () => { result.current.selectActor(ACTOR); });
    await ready(result);

    await act(async () => { result.current.setFilters({ actorUuid: '' }); });
    await ready(result);

    expect(result.current.selectedActor).toBeNull();
  });

  test('selectActor без uuid игнорируется', async () => {
    const { result } = setup();
    await ready(result);
    await act(async () => { result.current.selectActor({ fullName: 'Без UUID' }); });
    await ready(result);
    expect(result.current.selectedActor).toBeNull();
  });
});

describe('сброс и ручное обновление', () => {
  test('resetFilters чистит общий срез, все журналы и участника', async () => {
    const { result } = setup();
    await ready(result);

    await act(async () => {
      result.current.setFilters({ eventType: 'admin_role_add', order: 'asc' });
    });
    await act(async () => {
      result.current.selectActor({
        uuid: 'u-1', fullName: 'Тестовый', emailMasked: 't***@example.test',
      });
    });
    await act(async () => { result.current.setSource('data_change_log'); });
    await act(async () => { result.current.setFilters({ tableName: 'users' }); });
    await ready(result);

    const keyBefore = result.current.actorResetKey;
    await act(async () => { result.current.resetFilters(); });
    await ready(result);

    expect(result.current.filters.tableName).toBe('');
    expect(result.current.filters.order).toBe('desc');
    expect(result.current.selectedActor).toBeNull();
    expect(result.current.actorResetKey).toBeGreaterThan(keyBefore);
    expect(result.current.page).toBe(1);

    // Срез первого журнала тоже очищен.
    await act(async () => { result.current.setSource('audit_log'); });
    await ready(result);
    expect(result.current.filters.eventType).toBe('');
  });

  test('refetch не трогает ни фильтры, ни страницу', async () => {
    const { result } = setup();
    await ready(result);

    await act(async () => { result.current.setFilters({ outcome: 'failure' }); });
    await ready(result);
    await act(async () => { result.current.setPage(2); });
    await ready(result);

    const callsBefore = getAuditEvents.mock.calls.length;
    await act(async () => { result.current.refetch(); });
    await ready(result);

    expect(getAuditEvents.mock.calls.length).toBe(callsBefore + 1);
    expect(result.current.page).toBe(2);
    expect(result.current.filters.outcome).toBe('failure');
    expect(lastCall(getAuditEvents).page).toBe(2);
  });
});

describe('ошибки и устаревшие ответы', () => {
  test('ошибка запроса очищает строки и показывает сообщение', async () => {
    getAuditEvents.mockRejectedValueOnce(new Error('Журнал недоступен'));
    const { result } = setup();
    await waitFor(() => expect(result.current.error).toBe('Журнал недоступен'));
    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
  });

  test('устаревший ответ не перезаписывает более новый', async () => {
    let resolveSlow;
    getAuditEvents
      .mockImplementationOnce(() => new Promise((resolve) => { resolveSlow = resolve; }))
      .mockResolvedValueOnce(emptyPage({ items: [{ entry_id: 'new' }], total: 99 }));

    const { result } = setup();
    await act(async () => { result.current.setFilters({ outcome: 'failure' }); });
    await waitFor(() => expect(result.current.total).toBe(99));

    await act(async () => {
      resolveSlow(emptyPage({ items: [{ entry_id: 'old' }], total: 1 }));
      await Promise.resolve();
    });

    expect(result.current.total).toBe(99);
    expect(result.current.items[0].entry_id).toBe('new');
  });

  test('после размонтирования запросов и таймеров не остаётся', async () => {
    jest.useFakeTimers();
    const { result, unmount } = setup();
    await ready(result);
    const callsBefore = getAuditEvents.mock.calls.length;

    unmount();
    jest.advanceTimersByTime(60000);

    expect(getAuditEvents.mock.calls.length).toBe(callsBefore);
    expect(jest.getTimerCount()).toBe(0);
    jest.useRealTimers();
  });
});

describe('клиентская валидация окна', () => {
  test('одна дата — ошибка без HTTP', async () => {
    const { result } = setup();
    await ready(result);
    const callsBefore = getAuditEvents.mock.calls.length;

    await act(async () => { result.current.setFilters({ dateTo: '' }); });
    await waitFor(() => expect(result.current.error).toBeTruthy());

    expect(getAuditEvents.mock.calls.length).toBe(callsBefore);
    expect(result.current.items).toEqual([]);
    expect(result.current.loading).toBe(false);
  });

  test('период больше максимума — ошибка без HTTP', async () => {
    const { result } = setup();
    await ready(result);
    const callsBefore = getAuditEvents.mock.calls.length;

    await act(async () => {
      result.current.setFilters({ dateFrom: '2020-01-01', dateTo: '2026-08-22' });
    });
    await waitFor(() => expect(result.current.error).toMatch(/90/));

    expect(getAuditEvents.mock.calls.length).toBe(callsBefore);
  });

  test('исправленный период снова выполняет запрос', async () => {
    const { result } = setup();
    await ready(result);

    await act(async () => { result.current.setFilters({ dateTo: '' }); });
    await waitFor(() => expect(result.current.error).toBeTruthy());

    await act(async () => {
      result.current.setFilters({ dateFrom: '2026-08-16', dateTo: '2026-08-22' });
    });
    await ready(result);

    expect(result.current.error).toBeNull();
    expect(lastCall(getAuditEvents).date_to).toBe('2026-08-22');
  });
});

describe('лимиты и справочник как явные аргументы', () => {
  test('подменённые limits меняют размер страницы и предел пагинации', async () => {
    getAuditEvents.mockResolvedValue(emptyPage({ items: [], total: 250000 }));

    const { result } = renderHook(() => useAdminAuditLogs({
      options: OPTIONS,
      limits: { ...FALLBACK_LIMITS, default_page_size: 50, max_result_window: 1000 },
    }));
    await ready(result);

    expect(result.current.size).toBe(50);
    expect(lastCall(getAuditEvents).size).toBe(50);
    // floor(1000 / 50) = 20 страниц вместо ceil(250000/50) = 5000.
    expect(result.current.totalPages).toBe(20);
    expect(result.current.windowLimited).toBe(true);
  });

  test('без справочника actor_kind не отправляется', async () => {
    const { result } = renderHook(() => useAdminAuditLogs({
      options: null, limits: FALLBACK_LIMITS,
    }));
    await ready(result);

    await act(async () => { result.current.setFilters({ actorKind: 'system' }); });
    await ready(result);

    expect(lastCall(getAuditEvents).actor_kind).toBe('');
  });

  test('загрузка справочника не вызывает второй запрос списка', async () => {
    const { result, rerender } = renderHook(
      ({ options }) => useAdminAuditLogs({ options, limits: FALLBACK_LIMITS }),
      { initialProps: { options: null } },
    );
    await ready(result);
    const callsBefore = getAuditEvents.mock.calls.length;

    rerender({ options: OPTIONS });
    await ready(result);

    expect(getAuditEvents.mock.calls.length).toBe(callsBefore);
  });
});

describe('опрос сервера не ведётся', () => {
  test('без действий пользователя повторных запросов нет', async () => {
    jest.useFakeTimers();
    const { result } = setup();
    await ready(result);
    const callsBefore = getAuditEvents.mock.calls.length;

    await act(async () => { jest.advanceTimersByTime(5 * 60 * 1000); });

    expect(getAuditEvents.mock.calls.length).toBe(callsBefore);
    jest.useRealTimers();
  });
});
