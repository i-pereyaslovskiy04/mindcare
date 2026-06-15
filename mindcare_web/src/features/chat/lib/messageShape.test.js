import { mergeMessages } from './messageShape';

const T1 = '2024-01-01T10:00:00.000Z';
const T2 = '2024-01-01T11:00:00.000Z';
const T3 = '2024-01-01T12:00:00.000Z';

describe('mergeMessages', () => {
  test('empty incoming returns existing unchanged', () => {
    const existing = [{ id: 1, createdAt: T1 }];
    expect(mergeMessages(existing, [])).toBe(existing);
  });

  test('empty existing + empty incoming → empty', () => {
    expect(mergeMessages([], [])).toEqual([]);
  });

  test('new messages are appended', () => {
    const existing = [{ id: 1, createdAt: T1 }];
    const incoming = [{ id: 2, createdAt: T2 }];
    const out = mergeMessages(existing, incoming);
    expect(out.map((m) => m.id)).toEqual([1, 2]);
  });

  test('dedupes by id (no duplicates)', () => {
    const existing = [{ id: 1, createdAt: T1 }];
    const incoming = [
      { id: 1, createdAt: T1 },
      { id: 2, createdAt: T2 },
    ];
    const out = mergeMessages(existing, incoming);
    expect(out.map((m) => m.id)).toEqual([1, 2]);
  });

  test('updates read_at (readAt) on an existing message', () => {
    const existing = [{ id: 1, createdAt: T1, readAt: null }];
    const incoming = [{ id: 1, createdAt: T1, readAt: T2 }];
    const out = mergeMessages(existing, incoming);
    expect(out).toHaveLength(1);
    expect(out[0].readAt).toBe(T2);
  });

  test('keeps ascending order by createdAt then id', () => {
    const existing = [{ id: 2, createdAt: T2 }];
    const incoming = [
      { id: 3, createdAt: T3 },
      { id: 1, createdAt: T1 },
    ];
    const out = mergeMessages(existing, incoming);
    expect(out.map((m) => m.id)).toEqual([1, 2, 3]);
  });

  test('incoming fields override existing for same id', () => {
    const existing = [{ id: 1, createdAt: T1, text: 'old', readAt: null }];
    const incoming = [{ id: 1, createdAt: T1, text: 'old', readAt: T2 }];
    const out = mergeMessages(existing, incoming);
    expect(out[0]).toMatchObject({ id: 1, text: 'old', readAt: T2 });
  });
});
