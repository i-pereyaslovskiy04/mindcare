import { act, renderHook, waitFor } from '@testing-library/react';
import { MIN_TERM_LENGTH, useAuditActorSearch } from './useAuditActorSearch';
import { getUsers } from '../../../../api/users.api';

jest.mock('../../../../api/users.api');

// Синтетические данные: реальных ПДн в фикстурах нет.
const RAW_USERS = [
  {
    id: 17,
    uuid: '11111111-1111-4111-8111-111111111111',
    full_name: 'Тестовый Пользователь',
    email: 'testovyy@example.test',
    deleted_at: null,
  },
  {
    id: 18,
    uuid: '22222222-2222-4222-8222-222222222222',
    full_name: 'Удалённый Аккаунт',
    email: 'deleted@example.test',
    deleted_at: '2026-01-01T00:00:00Z',
  },
];

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
  getUsers.mockResolvedValue({ items: RAW_USERS, total: 2, page: 1, size: 10 });
});

afterEach(() => {
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
});

/** Ввод строки + прокрутка debounce. */
async function type(result, value) {
  await act(async () => { result.current.setTerm(value); });
  await act(async () => { jest.advanceTimersByTime(300); });
}

describe('порог длины и debounce', () => {
  test('до истечения debounce запрос не уходит', async () => {
    const { result } = renderHook(() => useAuditActorSearch());
    await act(async () => { result.current.setTerm('Тест'); });
    await act(async () => { jest.advanceTimersByTime(299); });
    expect(getUsers).not.toHaveBeenCalled();
  });

  test('после 300 мс уходит ровно один запрос', async () => {
    const { result } = renderHook(() => useAuditActorSearch());
    await type(result, 'Тест');
    await waitFor(() => expect(result.current.results).toHaveLength(2));
    expect(getUsers).toHaveBeenCalledTimes(1);
  });

  test(`строка короче ${MIN_TERM_LENGTH} символов не ищется`, async () => {
    const { result } = renderHook(() => useAuditActorSearch());
    await type(result, 'Т');
    expect(getUsers).not.toHaveBeenCalled();
    expect(result.current.results).toEqual([]);
  });

  test('пробелы не считаются содержимым', async () => {
    const { result } = renderHook(() => useAuditActorSearch());
    await type(result, '   ');
    expect(getUsers).not.toHaveBeenCalled();
  });

  test('удалённые аккаунты включены в поиск', async () => {
    const { result } = renderHook(() => useAuditActorSearch());
    await type(result, 'Тест');
    await waitFor(() => expect(getUsers).toHaveBeenCalled());
    expect(getUsers).toHaveBeenCalledWith(
      expect.objectContaining({ include_deleted: true, size: 10, search: 'Тест' }),
    );
  });
});

describe('безопасная проекция результатов', () => {
  test('в состоянии нет внутреннего id и полного email', async () => {
    const { result } = renderHook(() => useAuditActorSearch());
    await type(result, 'Тест');
    await waitFor(() => expect(result.current.results).toHaveLength(2));

    const [first] = result.current.results;
    expect(Object.keys(first).sort()).toEqual([
      'emailMasked', 'fullName', 'isDeleted', 'uuid',
    ]);
    expect(first).not.toHaveProperty('id');
    expect(first).not.toHaveProperty('email');
    expect(first.emailMasked).toBe('t***@example.test');
    expect(JSON.stringify(result.current.results)).not.toContain('testovyy@');
    expect(JSON.stringify(result.current.results)).not.toContain('"id"');
  });

  test('удалённый аккаунт помечен флагом', async () => {
    const { result } = renderHook(() => useAuditActorSearch());
    await type(result, 'Тест');
    await waitFor(() => expect(result.current.results).toHaveLength(2));
    expect(result.current.results[0].isDeleted).toBe(false);
    expect(result.current.results[1].isDeleted).toBe(true);
  });
});

describe('состояния загрузки и ошибки', () => {
  test('ошибка запроса очищает результаты и показывает сообщение', async () => {
    getUsers.mockRejectedValueOnce(new Error('Сервис недоступен'));
    const { result } = renderHook(() => useAuditActorSearch());
    await type(result, 'Тест');
    await waitFor(() => expect(result.current.error).toBe('Сервис недоступен'));
    expect(result.current.results).toEqual([]);
    expect(result.current.loading).toBe(false);
  });

  test('пустая выдача — не ошибка', async () => {
    getUsers.mockResolvedValueOnce({ items: [], total: 0 });
    const { result } = renderHook(() => useAuditActorSearch());
    await type(result, 'Тест');
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.results).toEqual([]);
    expect(result.current.error).toBeNull();
  });
});

describe('устаревшие ответы', () => {
  test('поздний ответ после reset() НЕ возвращает результаты обратно', async () => {
    let resolveSlow;
    getUsers.mockImplementationOnce(
      () => new Promise((resolve) => { resolveSlow = resolve; }),
    );

    const { result } = renderHook(() => useAuditActorSearch());
    await type(result, 'Тест');
    expect(getUsers).toHaveBeenCalledTimes(1);

    // Пользователь сбросил выбор, пока запрос ещё в полёте.
    await act(async () => { result.current.reset(); });
    expect(result.current.results).toEqual([]);

    await act(async () => {
      resolveSlow({ items: RAW_USERS, total: 2 });
      await Promise.resolve();
    });

    expect(result.current.results).toEqual([]);
    expect(result.current.loading).toBe(false);
  });

  test('ответ по старой строке не перезаписывает более новый', async () => {
    let resolveFirst;
    getUsers
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce({
        items: [RAW_USERS[1]], total: 1,
      });

    const { result } = renderHook(() => useAuditActorSearch());
    await type(result, 'Стар');
    await type(result, 'Новый');
    await waitFor(() => expect(result.current.results).toHaveLength(1));

    await act(async () => {
      resolveFirst({ items: RAW_USERS, total: 2 });
      await Promise.resolve();
    });

    expect(result.current.results).toHaveLength(1);
    expect(result.current.results[0].uuid).toBe(RAW_USERS[1].uuid);
  });

  test('переход ниже порога длины очищает выдачу и глушит ответ в полёте', async () => {
    let resolveSlow;
    getUsers.mockImplementationOnce(
      () => new Promise((resolve) => { resolveSlow = resolve; }),
    );

    const { result } = renderHook(() => useAuditActorSearch());
    await type(result, 'Тест');
    await type(result, 'Т');
    expect(result.current.results).toEqual([]);

    await act(async () => {
      resolveSlow({ items: RAW_USERS, total: 2 });
      await Promise.resolve();
    });

    expect(result.current.results).toEqual([]);
  });
});

describe('reset', () => {
  test('очищает строку, результаты и ошибку', async () => {
    const { result } = renderHook(() => useAuditActorSearch());
    await type(result, 'Тест');
    await waitFor(() => expect(result.current.results).toHaveLength(2));

    await act(async () => { result.current.reset(); });

    expect(result.current.term).toBe('');
    expect(result.current.results).toEqual([]);
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
  });
});
