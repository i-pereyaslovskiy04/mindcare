import {
  SYSTEM_DIALOG_ID,
  SYSTEM_EMPTY_TEXT,
  SYSTEM_MESSAGE_MARKER,
  SYSTEM_MONOGRAM,
  SYSTEM_NOTICE,
  SYSTEM_SECTION_TITLE,
  SYSTEM_SENDER_NAME,
  hasPresence,
  isSystemDeepLink,
  omitSearchParams,
  splitConversations,
  systemContact,
} from './conversationView';

describe('deep-link на системную беседу', () => {
  test('isSystemDeepLink: только system=1', () => {
    expect(isSystemDeepLink(new URLSearchParams('system=1'))).toBe(true);
    expect(isSystemDeepLink(new URLSearchParams('system=1&student=7'))).toBe(true);
    expect(isSystemDeepLink(new URLSearchParams(''))).toBe(false);
    expect(isSystemDeepLink(new URLSearchParams('system=0'))).toBe(false);
    expect(isSystemDeepLink(new URLSearchParams('system='))).toBe(false);
    expect(isSystemDeepLink(new URLSearchParams('conversation=conv-1'))).toBe(false);
  });

  test('omitSearchParams убирает только перечисленные ключи', () => {
    const params = new URLSearchParams('system=1&conversation=conv-1&tab=x');
    expect(omitSearchParams(params, ['system'])).toEqual({ conversation: 'conv-1', tab: 'x' });
    expect(omitSearchParams(params, ['conversation', 'student'])).toEqual({ system: '1', tab: 'x' });
    expect(omitSearchParams(new URLSearchParams('system=1'), ['system'])).toEqual({});
  });
});

describe('контракт системной беседы (SYSTEM MESSAGE, не NOTIFICATION)', () => {
  test('единые подписи', () => {
    expect(SYSTEM_SENDER_NAME).toBe('Психология ДонГУ');
    expect(SYSTEM_MESSAGE_MARKER).toBe('Системное сообщение');
    expect(SYSTEM_SECTION_TITLE).toBe('Системные сообщения');
    expect(SYSTEM_MONOGRAM).toBe('ПД');
    expect(SYSTEM_NOTICE).toBe('Это системные сообщения Психологии ДонГУ. Ответить на них нельзя.');
    expect(SYSTEM_EMPTY_TEXT).toBe('Системных сообщений пока нет.');
  });

  test('systemContact: имя «Психология ДонГУ», маркер и статичное превью', () => {
    const c = systemContact({ last_message_at: null, unread_count: 2 });
    expect(c).toMatchObject({
      id: SYSTEM_DIALOG_ID,
      system: true,
      name: 'Психология ДонГУ',
      role: 'Системное сообщение',
      lastMsg: 'Системное сообщение',
      unread: 2,
    });
    expect(JSON.stringify(c)).not.toMatch(/MindCare|уведомлен/i);
  });
});

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
