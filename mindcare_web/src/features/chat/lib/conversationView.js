/**
 * Хелперы представления списка диалогов (общие для student/psychologist).
 */

export const SYSTEM_DIALOG_ID = '__system__';

// Единый контракт отображения системной беседы. Это SYSTEM MESSAGE —
// постоянные записи в беседе «Психология ДонГУ», а не NOTIFICATION: слово
// «уведомления» и колокольчик зарезервированы за будущими уведомлениями шапки.
export const SYSTEM_SENDER_NAME = 'Психология ДонГУ';
export const SYSTEM_MESSAGE_MARKER = 'Системное сообщение';
export const SYSTEM_SECTION_TITLE = 'Системные сообщения';
export const SYSTEM_MONOGRAM = 'ПД';
export const SYSTEM_NOTICE =
  'Это системные сообщения Психологии ДонГУ. Ответить на них нельзя.';
export const SYSTEM_EMPTY_TEXT = 'Системных сообщений пока нет.';

export function initialsOf(name) {
  return (name || '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('');
}

export function formatLastTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toDateString() === new Date().toDateString()
    ? d.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString('ru', { day: 'numeric', month: 'short' });
}

/**
 * Делит engagement-беседы на архив и активные (Stage 31s).
 *
 * - active   — engagement_status === 'active' (показываются всегда);
 * - archived — закрытые/переведённые; backend (Stage 31p) уже отдаёт сюда
 *              только non-empty inactive, пустые inactive скрыты;
 * - system   — служебная беседа сюда не относится; на всякий случай
 *              отфильтровывается, чтобы НИКОГДА не попасть в архив.
 *
 * Возвращает { archived, active, system }. Порядок внутри групп сохраняется.
 */
export function hasPresence(contact) {
  return !contact?.system && typeof contact?.online === 'boolean';
}

export function splitConversations(conversations) {
  const archived = [];
  const active = [];
  const system = [];
  for (const c of conversations || []) {
    if (c.type === 'system') {
      system.push(c);
      continue;
    }
    const status = c.engagement_status ?? c.engagementStatus;
    if (status === 'active') active.push(c);
    else archived.push(c);
  }
  return { archived, active, system };
}

/** Sidebar-контакт для системной беседы (закрепляется сверху списка). */
export function systemContact(sysConv) {
  return {
    id: SYSTEM_DIALOG_ID,
    system: true,
    name: SYSTEM_SENDER_NAME,
    initials: '',
    role: SYSTEM_MESSAGE_MARKER,
    // Статичное превью: реальный текст последнего сообщения — отдельный этап.
    lastMsg: SYSTEM_MESSAGE_MARKER,
    time: formatLastTime(sysConv?.last_message_at),
    unread: sysConv?.unread_count || 0,
  };
}

/**
 * Deep-link на системную беседу: `/student/chat?system=1`,
 * `/psychologist/chat?system=1`. Страница Messenger открывает беседу тем же
 * путём, что и клик по ней в списке, и затем убирает параметр (replace).
 * Другие значения параметра ничего не открывают.
 */
export const SYSTEM_QUERY_PARAM = 'system';

export function isSystemDeepLink(searchParams) {
  return searchParams.get(SYSTEM_QUERY_PARAM) === '1';
}

/**
 * Параметры запроса без перечисленных ключей — plain-объект для
 * setSearchParams. Остальные параметры сохраняются: каждый deep-link убирает
 * только свои ключи, не затирая чужие до их обработки.
 */
export function omitSearchParams(searchParams, keys) {
  return Object.fromEntries(
    [...searchParams.entries()].filter(([key]) => !keys.includes(key)),
  );
}
