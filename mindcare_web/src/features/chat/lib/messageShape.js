/**
 * Единая UI-форма сообщения для всех chat-страниц (student/psychologist/system).
 *
 * Backend ChatMessageRead → { id, text, mine, system, time, createdAt, readAt }.
 *   mine   — рисуем справа («моё»), показываем read receipts;
 *   system — message_kind='system' (sender_role='system'): нейтральный стиль,
 *            без аватара, без receipts, не «моё».
 */

export function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
}

export function mapApiMessage(m) {
  return {
    id: m.id,
    text: m.content,
    mine: m.is_mine === true,
    system: m.sender_role === 'system',
    time: formatTime(m.created_at),
    createdAt: m.created_at,
    readAt: m.read_at || null,
  };
}
