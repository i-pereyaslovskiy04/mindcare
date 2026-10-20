/**
 * Представление колокольчика шапки. Колокольчик — не отдельная система
 * уведомлений, а слой над системной беседой «Психология ДонГУ»: badge — её
 * unread_count, список — непрочитанные сообщения этой беседы.
 */
import { replaceInternalLinks } from '../../chat/lib/internalLinks';
import { SYSTEM_QUERY_PARAM } from '../../chat/lib/conversationView';

/** Сколько непрочитанных показывает панель. */
export const BELL_LIMIT = 5;

export const BELL_TITLE = 'Уведомления';
export const BELL_EMPTY_TEXT = 'Новых уведомлений нет';
export const BELL_ERROR_TEXT = 'Не удалось загрузить уведомления.';
export const BELL_SHOW_ALL = 'Показать все';

/** Кабинеты, в которых есть колокольчик (и Messenger с системной беседой). */
const BELL_CABINETS = new Set(['student', 'psychologist']);

export function hasBell(cabinetRole) {
  return BELL_CABINETS.has(cabinetRole);
}

/** Системная беседа в Messenger кабинета (deep-link `?system=1`). */
export function systemChatHref(cabinetRole) {
  return hasBell(cabinetRole) ? `/${cabinetRole}/chat?${SYSTEM_QUERY_PARAM}=1` : null;
}

/** Текст badge: null — badge не показывается. */
export function badgeText(count) {
  if (!(count > 0)) return null;
  return count > 99 ? '99+' : String(count);
}

/** Доступное имя кнопки: точное число, без «99+». */
export function bellLabel(count) {
  return count > 0 ? `${BELL_TITLE}, новых: ${count}` : BELL_TITLE;
}

/**
 * До `limit` непрочитанных, новые сверху. Endpoint отдаёт последние сообщения
 * беседы по возрастанию id; mark-read отмечает прочитанной всю беседу сразу,
 * поэтому непрочитанные — это хвост беседы, и последних `limit` сообщений
 * достаточно, чтобы получить самые новые непрочитанные.
 */
export function pickUnread(items, limit = BELL_LIMIT) {
  return (items || [])
    .filter((m) => !m.read_at && !m.is_deleted)
    .reverse()
    .slice(0, limit)
    .map((m) => ({
      id: m.id,
      text: previewText(m.content),
      createdAt: m.created_at,
    }));
}

/** Превью: внутренние пути — подписью из allowlist, пробелы схлопнуты. */
export function previewText(content) {
  return replaceInternalLinks(content || '').replace(/\s+/g, ' ').trim();
}

/** Время пункта: сегодня — «14:05», иначе — «12 окт., 14:05». */
export function formatBellTime(iso, now = new Date()) {
  if (!iso) return '';
  const d = new Date(iso);
  const time = d.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === now.toDateString()) return time;
  return `${d.toLocaleDateString('ru', { day: 'numeric', month: 'short' })}, ${time}`;
}
