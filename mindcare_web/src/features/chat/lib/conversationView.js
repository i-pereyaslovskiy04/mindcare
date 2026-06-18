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
    name: 'Системные уведомления',
    initials: '',
    role: 'Системные уведомления',
    lastMsg: 'Уведомления MindCare',
    time: formatLastTime(sysConv?.last_message_at),
    unread: sysConv?.unread_count || 0,
  };
}
