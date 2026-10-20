import {
  BELL_LIMIT,
  badgeText,
  bellLabel,
  formatBellTime,
  hasBell,
  pickUnread,
  previewText,
  systemChatHref,
} from './bellView';

const msg = (id, readAt = null, extra = {}) => ({
  id,
  content: `Сообщение ${id}`,
  created_at: `2026-10-20T10:0${id % 10}:00Z`,
  read_at: readAt,
  ...extra,
});

describe('bellView', () => {
  test('колокольчик есть только у student и psychologist', () => {
    expect(hasBell('student')).toBe(true);
    expect(hasBell('psychologist')).toBe(true);
    expect(hasBell('supervisor')).toBe(false);
    expect(hasBell('admin')).toBe(false);
    expect(hasBell(undefined)).toBe(false);
  });

  test('ссылка — системная беседа Messenger кабинета (?system=1)', () => {
    expect(systemChatHref('student')).toBe('/student/chat?system=1');
    expect(systemChatHref('psychologist')).toBe('/psychologist/chat?system=1');
    expect(systemChatHref('supervisor')).toBeNull();
  });

  test('badge: 0/null — нет, 1–99 — число, больше — «99+»', () => {
    expect(badgeText(0)).toBeNull();
    expect(badgeText(null)).toBeNull();
    expect(badgeText(undefined)).toBeNull();
    expect(badgeText(1)).toBe('1');
    expect(badgeText(99)).toBe('99');
    expect(badgeText(100)).toBe('99+');
  });

  test('доступное имя — с точным числом', () => {
    expect(bellLabel(0)).toBe('Уведомления');
    expect(bellLabel(null)).toBe('Уведомления');
    expect(bellLabel(3)).toBe('Уведомления, новых: 3');
    expect(bellLabel(150)).toBe('Уведомления, новых: 150');
  });

  test('pickUnread: только непрочитанные, новые сверху, не больше лимита', () => {
    const items = [msg(1, '2026-10-20T11:00:00Z'), msg(2), msg(3), msg(4)];
    expect(pickUnread(items).map((m) => m.id)).toEqual([4, 3, 2]);

    const many = Array.from({ length: 8 }, (_, i) => msg(i + 1));
    expect(pickUnread(many).map((m) => m.id)).toEqual([8, 7, 6, 5, 4]);
    expect(BELL_LIMIT).toBe(5);

    expect(pickUnread([msg(1, '2026-10-20T11:00:00Z')])).toEqual([]);
    expect(pickUnread(undefined)).toEqual([]);
    expect(pickUnread([msg(5, null, { is_deleted: true })])).toEqual([]);
  });

  test('pickUnread не меняет исходный массив', () => {
    const items = [msg(1), msg(2)];
    pickUnread(items);
    expect(items.map((m) => m.id)).toEqual([1, 2]);
  });

  test('превью: внутренний путь — подписью, без сырого URL', () => {
    const text = 'Подтвердите статус: /student/settings#student-verification.';
    expect(previewText(text)).toBe('Подтвердите статус: Подтверждение студента ДонГУ.');
    expect(previewText(text)).not.toMatch('/student/settings');
    expect(previewText('Строка\n\nвторая   строка ')).toBe('Строка вторая строка');
    expect(previewText(null)).toBe('');
  });

  test('время: сегодня — только часы, иначе — дата и часы', () => {
    const now = new Date(2026, 9, 20, 15, 0);
    expect(formatBellTime(new Date(2026, 9, 20, 9, 5).toISOString(), now)).toBe('09:05');
    const other = formatBellTime(new Date(2026, 9, 12, 14, 30).toISOString(), now);
    expect(other).toMatch(/^12 окт\.?, 14:30$/);
    expect(formatBellTime(null, now)).toBe('');
  });
});
