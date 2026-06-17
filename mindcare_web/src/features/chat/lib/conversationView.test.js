import { hasPresence, splitConversations } from './conversationView';

describe('hasPresence', () => {
  test('shows presence for non-system contacts with boolean online state', () => {
    expect(hasPresence({ system: false, online: true })).toBe(true);
    expect(hasPresence({ online: false })).toBe(true);
  });

  test('hides presence for system contacts and non-boolean online state', () => {
    expect(hasPresence({ system: true, online: true })).toBe(false);
    expect(hasPresence({ system: false })).toBe(false);
    expect(hasPresence({ system: false, online: null })).toBe(false);
    expect(hasPresence(null)).toBe(false);
  });
});

describe('splitConversations', () => {
  test('active conversations go to active, inactive to archived', () => {
    const convs = [
      { uuid: 'a', engagement_status: 'active' },
      { uuid: 'b', engagement_status: 'transferred' },
      { uuid: 'c', engagement_status: 'completed' },
      { uuid: 'd', engagement_status: 'active' },
    ];
    const { active, archived, system } = splitConversations(convs);
    expect(active.map((c) => c.uuid)).toEqual(['a', 'd']);
    expect(archived.map((c) => c.uuid)).toEqual(['b', 'c']);
    expect(system).toEqual([]);
  });

  test('system conversation never goes to archive or active', () => {
    const convs = [
      { uuid: 's', type: 'system' },
      { uuid: 'a', engagement_status: 'active' },
      { uuid: 'b', engagement_status: 'completed' },
    ];
    const { active, archived, system } = splitConversations(convs);
    expect(system.map((c) => c.uuid)).toEqual(['s']);
    expect(active.map((c) => c.uuid)).toEqual(['a']);
    expect(archived.map((c) => c.uuid)).toEqual(['b']);
  });

  test('empty / null input → empty groups (no archive shown)', () => {
    expect(splitConversations([])).toEqual({ archived: [], active: [], system: [] });
    expect(splitConversations(undefined)).toEqual({ archived: [], active: [], system: [] });
  });

  test('supports camelCase engagementStatus too', () => {
    const { active, archived } = splitConversations([
      { uuid: 'a', engagementStatus: 'active' },
      { uuid: 'b', engagementStatus: 'transferred' },
    ]);
    expect(active.map((c) => c.uuid)).toEqual(['a']);
    expect(archived.map((c) => c.uuid)).toEqual(['b']);
  });

  test('order within groups is preserved', () => {
    const { archived } = splitConversations([
      { uuid: 'x', engagement_status: 'completed' },
      { uuid: 'y', engagement_status: 'transferred' },
    ]);
    expect(archived.map((c) => c.uuid)).toEqual(['x', 'y']);
  });
});
