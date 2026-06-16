import { mapApiMessage, mergeMessages, shouldShowAuthorHeader } from './messageShape';

const T1 = '2024-01-01T10:00:00.000Z';
const T2 = '2024-01-01T11:00:00.000Z';
const T3 = '2024-01-01T12:00:00.000Z';

describe('mapApiMessage', () => {
  test('keeps uuid and maps editedAt (Stage 31x)', () => {
    const out = mapApiMessage({
      id: 5,
      uuid: 'm-uuid-5',
      content: 'привет',
      is_mine: true,
      sender_role: 'student',
      sender_id: 9,
      created_at: T1,
      read_at: null,
      edited_at: T2,
    });
    expect(out.uuid).toBe('m-uuid-5');
    expect(out.editedAt).toBe(T2);
    expect(out.text).toBe('привет');
    expect(out.mine).toBe(true);
  });

  test('editedAt is null when not edited', () => {
    const out = mapApiMessage({
      id: 6,
      uuid: 'm-uuid-6',
      content: 'x',
      is_mine: false,
      sender_role: 'psychologist',
      sender_id: 3,
      created_at: T1,
      read_at: null,
      edited_at: null,
    });
    expect(out.editedAt).toBeNull();
  });

  test('maps is_deleted → deleted (Stage 31y)', () => {
    const del = mapApiMessage({
      id: 7, uuid: 'm-uuid-7', content: '', is_mine: true,
      sender_role: 'student', sender_id: 9, created_at: T1,
      read_at: null, edited_at: null, is_deleted: true,
    });
    expect(del.deleted).toBe(true);

    const live = mapApiMessage({
      id: 8, uuid: 'm-uuid-8', content: 'жив', is_mine: true,
      sender_role: 'student', sender_id: 9, created_at: T1,
      read_at: null, edited_at: null,
    });
    expect(live.deleted).toBe(false);
  });
});

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

describe('shouldShowAuthorHeader', () => {
  // близкие по времени сообщения одной даты, чтобы исключить gap-триггер
  const a = '2024-01-01T10:00:00.000Z';
  const b = '2024-01-01T10:00:30.000Z';
  const c = '2024-01-01T10:01:00.000Z';

  test('A. header shown for the first message', () => {
    const msgs = [{ id: 1, senderId: 7, createdAt: a }];
    expect(shouldShowAuthorHeader(msgs, 0)).toBe(true);
  });

  test('B. header NOT repeated for consecutive same-sender messages', () => {
    const msgs = [
      { id: 1, senderId: 7, createdAt: a },
      { id: 2, senderId: 7, createdAt: b },
      { id: 3, senderId: 7, createdAt: c },
    ];
    expect(shouldShowAuthorHeader(msgs, 1)).toBe(false);
    expect(shouldShowAuthorHeader(msgs, 2)).toBe(false);
  });

  test('C. header appears when sender changes', () => {
    const msgs = [
      { id: 1, senderId: 7, createdAt: a },
      { id: 2, senderId: 9, createdAt: b },
    ];
    expect(shouldShowAuthorHeader(msgs, 1)).toBe(true);
  });

  test('falls back to mine flag when senderId is absent', () => {
    const msgs = [
      { id: 1, mine: false, createdAt: a },
      { id: 2, mine: true, createdAt: b },
      { id: 3, mine: true, createdAt: c },
    ];
    expect(shouldShowAuthorHeader(msgs, 1)).toBe(true);
    expect(shouldShowAuthorHeader(msgs, 2)).toBe(false);
  });

  test('header appears after a system message', () => {
    const msgs = [
      { id: 1, senderId: 7, createdAt: a },
      { id: 2, system: true, createdAt: b },
      { id: 3, senderId: 7, createdAt: c },
    ];
    expect(shouldShowAuthorHeader(msgs, 2)).toBe(true);
  });

  test('header never shown for a system message itself', () => {
    const msgs = [{ id: 1, system: true, createdAt: a }];
    expect(shouldShowAuthorHeader(msgs, 0)).toBe(false);
  });

  test('header appears on a new calendar date', () => {
    const msgs = [
      { id: 1, senderId: 7, createdAt: '2024-01-01T22:00:00.000Z' },
      { id: 2, senderId: 7, createdAt: '2024-01-02T09:00:00.000Z' },
    ];
    expect(shouldShowAuthorHeader(msgs, 1)).toBe(true);
  });

  test('header appears after a large time gap from same sender', () => {
    const msgs = [
      { id: 1, senderId: 7, createdAt: '2024-01-01T10:00:00.000Z' },
      { id: 2, senderId: 7, createdAt: '2024-01-01T10:30:00.000Z' },
    ];
    expect(shouldShowAuthorHeader(msgs, 1)).toBe(true);
  });
});
