import { mapApiMessage, mergeMessages, reconcileMessagesSnapshot, shouldShowAuthorHeader } from './messageShape';

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

describe('reconcileMessagesSnapshot', () => {
  // Helpers: makeMsg(id, overrides)
  const t = (n) => `2024-01-01T10:0${n}:00.000Z`;
  const msg = (id, extra = {}) => ({ id, createdAt: t(id), ...extra });

  test('removes a middle message absent from snapshot window', () => {
    const current = [msg(1), msg(2), msg(3)];
    // id=2 is deleted — not in snapshot
    const snapshot = [msg(1), msg(3)];
    const result = reconcileMessagesSnapshot(current, snapshot);
    expect(result.map((m) => m.id)).toEqual([1, 3]);
  });

  test('removes the last message when absent from snapshot (knownMaxId required)', () => {
    const current = [msg(1), msg(2), msg(3)];
    // id=3 deleted; snapshot max=2; knownMaxId=3 → id=3 ≤ knownMaxId → removed
    const snapshot = [msg(1), msg(2)];
    const result = reconcileMessagesSnapshot(current, snapshot, 3);
    expect(result.map((m) => m.id)).toEqual([1, 2]);
  });

  test('updates an edited message from snapshot', () => {
    const current = [msg(1, { editedAt: null, text: 'original' })];
    const snapshot = [msg(1, { editedAt: t(5), text: 'edited' })];
    const result = reconcileMessagesSnapshot(current, snapshot);
    expect(result).toHaveLength(1);
    expect(result[0].editedAt).toBe(t(5));
    expect(result[0].text).toBe('edited');
  });

  test('adds a new message from snapshot', () => {
    const current = [msg(1)];
    const snapshot = [msg(1), msg(2)];
    const result = reconcileMessagesSnapshot(current, snapshot);
    expect(result.map((m) => m.id)).toEqual([1, 2]);
  });

  test('preserves ascending sort order after reconcile', () => {
    // current in wrong order, id=2 deleted
    const current = [msg(3), msg(1), msg(2)];
    const snapshot = [msg(1), msg(3)];
    const result = reconcileMessagesSnapshot(current, snapshot, 3);
    expect(result.map((m) => m.id)).toEqual([1, 3]);
  });

  test('keeps history messages below snapshot window unchanged', () => {
    // History: ids 1-5; snapshot window covers [3, 5]; id=4 deleted
    const current = [msg(1), msg(2), msg(3), msg(4), msg(5)];
    const snapshot = [msg(3), msg(5)]; // id=4 absent (deleted), minId=3 maxId=5
    const result = reconcileMessagesSnapshot(current, snapshot);
    // ids 1,2 < minId=3 → kept; id=3,5 in snapshot → kept; id=4 in [3,5] not in snapshot → removed
    expect(result.map((m) => m.id)).toEqual([1, 2, 3, 5]);
  });

  test('protects a message sent concurrently during in-flight poll', () => {
    // id=3 was sent AFTER pollNew captured knownMaxId=2, before GET returned
    const current = [msg(1), msg(2), msg(3)];
    const snapshot = [msg(1), msg(2)]; // server not yet aware of id=3
    // knownMaxId=2 → id=3 > maxSnapshotId=2 AND id=3 > knownMaxId=2 → keep
    const result = reconcileMessagesSnapshot(current, snapshot, 2);
    expect(result.map((m) => m.id)).toEqual([1, 2, 3]);
  });

  test('returns currentMessages reference unchanged when snapshot is empty', () => {
    const current = [msg(1), msg(2)];
    const result = reconcileMessagesSnapshot(current, []);
    expect(result).toBe(current);
  });

  test('handles single-message conversation where that message is deleted', () => {
    const current = [msg(1)];
    // snapshot is empty (the only message was deleted) → safe fallback: no reconcile
    const result = reconcileMessagesSnapshot(current, []);
    expect(result).toBe(current); // not cleared — empty snapshot is ambiguous
  });

  test('snapshot with all new messages (local was empty) returns snapshot', () => {
    const result = reconcileMessagesSnapshot([], [msg(1), msg(2)]);
    expect(result.map((m) => m.id)).toEqual([1, 2]);
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

  test('header shown for a system message like any other first message', () => {
    const msgs = [{ id: 1, system: true, createdAt: a }];
    expect(shouldShowAuthorHeader(msgs, 0)).toBe(true);
  });

  test('header not repeated for consecutive system messages', () => {
    const msgs = [
      { id: 1, system: true, createdAt: a },
      { id: 2, system: true, createdAt: b },
    ];
    expect(shouldShowAuthorHeader(msgs, 1)).toBe(false);
  });

  test('header appears when switching from a system message to a human sender', () => {
    const msgs = [
      { id: 1, system: true, createdAt: a },
      { id: 2, senderId: 7, createdAt: b },
    ];
    expect(shouldShowAuthorHeader(msgs, 1)).toBe(true);
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
