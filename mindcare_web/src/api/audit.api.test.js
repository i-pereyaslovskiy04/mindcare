import {
  getAuditEvents, getAuditOptions, getAuthEvents, getDataChanges,
} from './audit.api';
import * as auditApi from './audit.api';
import { apiFetch } from './client';

jest.mock('./client');

beforeEach(() => {
  jest.clearAllMocks();
  apiFetch.mockResolvedValue({ items: [], total: 0, page: 1, size: 20 });
});

/** URL последнего вызова → URLSearchParams. */
function lastParams() {
  const [url] = apiFetch.mock.calls[apiFetch.mock.calls.length - 1];
  return new URLSearchParams(url.split('?')[1] ?? '');
}

function lastPath() {
  const [url] = apiFetch.mock.calls[apiFetch.mock.calls.length - 1];
  return url.split('?')[0];
}

const BASE_QUERY = {
  page: 1,
  size: 20,
  date_from: '2026-08-16',
  date_to: '2026-08-22',
  order: 'desc',
};

describe('endpoints', () => {
  test('каждая функция бьёт в свой путь', () => {
    getAuditOptions();
    expect(lastPath()).toBe('/api/admin/audit/options');

    getAuditEvents(BASE_QUERY);
    expect(lastPath()).toBe('/api/admin/audit/events');

    getAuthEvents(BASE_QUERY);
    expect(lastPath()).toBe('/api/admin/audit/auth-events');

    getDataChanges(BASE_QUERY);
    expect(lastPath()).toBe('/api/admin/audit/data-changes');
  });

  test('options не принимает и не сериализует параметры', () => {
    getAuditOptions();
    const [url, opts] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/admin/audit/options');
    expect(opts).toBeUndefined();
  });

  test('модуль не содержит функций экспорта или скачивания', () => {
    const names = Object.keys(auditApi).join(' ').toLowerCase();
    expect(names).not.toMatch(/export|download|blob|csv|excel|pdf/);
  });
});

describe('allowlist параметров', () => {
  test('общие параметры уходят на всех трёх эндпоинтах', () => {
    getAuditEvents(BASE_QUERY);
    const params = lastParams();
    expect(params.get('page')).toBe('1');
    expect(params.get('size')).toBe('20');
    expect(params.get('date_from')).toBe('2026-08-16');
    expect(params.get('date_to')).toBe('2026-08-22');
    expect(params.get('order')).toBe('desc');
  });

  test('неизвестные поля отбрасываются', () => {
    getAuditEvents({
      ...BASE_QUERY,
      junk: 'x',
      sort: 'event_type',
      category: 'users_roles',
      target_user_uuid: '11111111-1111-1111-1111-111111111111',
    });
    const params = lastParams();
    expect(params.has('junk')).toBe(false);
    expect(params.has('sort')).toBe(false);
    // Категория — frontend-only группировка опций, а не фильтр API.
    expect(params.has('category')).toBe(false);
    // target_user_uuid в UI не используется и в allowlist не входит.
    expect(params.has('target_user_uuid')).toBe(false);
  });

  test('фильтр чужого журнала не попадает в запрос', () => {
    getAuthEvents({ ...BASE_QUERY, actor_role: 'admin', event_type: 'login' });
    const params = lastParams();
    // auth_log роль актора не хранит; event_type — ключ другого журнала.
    expect(params.has('actor_role')).toBe(false);
    expect(params.has('event_type')).toBe(false);
  });

  test('data-changes принимает свои ключи и не принимает чужие', () => {
    getDataChanges({
      ...BASE_QUERY,
      table_name: 'meeting_types',
      operation: 'UPDATE',
      record_id: 42,
      event_type: 'admin_role_add',
    });
    const params = lastParams();
    expect(params.get('table_name')).toBe('meeting_types');
    expect(params.get('operation')).toBe('UPDATE');
    expect(params.get('record_id')).toBe('42');
    expect(params.has('event_type')).toBe(false);
  });
});

describe('пропуск незаданных значений', () => {
  test('null / undefined / пустая строка не отправляются', () => {
    getAuditEvents({
      ...BASE_QUERY,
      actor_uuid: '',
      actor_kind: null,
      actor_role: undefined,
      event_type: '',
      entity_id: null,
    });
    const params = lastParams();
    expect(params.has('actor_uuid')).toBe(false);
    expect(params.has('actor_kind')).toBe(false);
    expect(params.has('actor_role')).toBe(false);
    expect(params.has('event_type')).toBe(false);
    expect(params.has('entity_id')).toBe(false);
  });

  test('success=false ОТПРАВЛЯЕТСЯ (истинностная проверка потеряла бы его)', () => {
    getAuthEvents({ ...BASE_QUERY, success: false });
    expect(lastParams().get('success')).toBe('false');
  });

  test('success=true отправляется', () => {
    getAuthEvents({ ...BASE_QUERY, success: true });
    expect(lastParams().get('success')).toBe('true');
  });

  test('include_access_events отправляется в обоих значениях', () => {
    getAuditEvents({ ...BASE_QUERY, include_access_events: true });
    expect(lastParams().get('include_access_events')).toBe('true');

    getAuditEvents({ ...BASE_QUERY, include_access_events: false });
    expect(lastParams().get('include_access_events')).toBe('false');
  });

  test('числовой идентификатор не теряется сериализатором', () => {
    // Диапазон проверяет parseRecordRef ДО вызова API; здесь важно лишь то,
    // что число доходит до query как есть.
    getAuditEvents({ ...BASE_QUERY, entity_type: 'appointment', entity_id: 7 });
    expect(lastParams().get('entity_id')).toBe('7');
  });
});

describe('участник адресуется только UUID', () => {
  test('actor_uuid уходит как есть', () => {
    const uuid = '3f1a5c22-0000-4000-8000-1234567890ab';
    getAuditEvents({ ...BASE_QUERY, actor_uuid: uuid });
    expect(lastParams().get('actor_uuid')).toBe(uuid);
  });

  test('имя и email пользователя не попадают в запрос ни под каким ключом', () => {
    getAuditEvents({
      ...BASE_QUERY,
      actor_uuid: '3f1a5c22-0000-4000-8000-1234567890ab',
      search: 'Тестовый Пользователь',
      email: 'u***@example.test',
      full_name: 'Тестовый Пользователь',
      q: 'Тестовый',
    });
    const raw = apiFetch.mock.calls[apiFetch.mock.calls.length - 1][0];
    expect(raw).not.toMatch(/Тестовый/);
    expect(raw).not.toMatch(/example\.test/);
    expect(decodeURIComponent(raw)).not.toMatch(/Тестовый/);
  });
});
