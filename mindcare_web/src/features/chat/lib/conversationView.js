/**
 * Хелперы представления списка диалогов (общие для student/psychologist).
 */

export const SYSTEM_DIALOG_ID = '__system__';
export const SYSTEM_NOTICE =
  'Это системные уведомления. Ответить в этот диалог нельзя.';

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

/** Sidebar-контакт для системной беседы (закрепляется сверху списка). */
export function systemContact(sysConv) {
  return {
    id: SYSTEM_DIALOG_ID,
    system: true,
    name: 'Системные уведомления',
    initials: '',
    role: 'Системные уведомления',
    lastMsg: 'Уведомления MindCare',
    time: formatLastTime(sysConv?.last_message_at),
    unread: sysConv?.unread_count || 0,
  };
}
