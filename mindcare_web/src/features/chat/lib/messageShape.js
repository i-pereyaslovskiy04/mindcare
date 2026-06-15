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

/**
 * Сливает текущий список сообщений со снапшотом (live refresh):
 *   - новые id добавляются;
 *   - существующие обновляются (важно для read_at/readAt → ✓✓);
 *   - дубликатов нет;
 *   - порядок по createdAt, fallback по id.
 * Чистая функция: incoming перезаписывает поля existing.
 */
export function mergeMessages(existing, incoming) {
  if (!incoming || incoming.length === 0) return existing;
  const byId = new Map();
  for (const m of existing) byId.set(m.id, m);
  for (const m of incoming) {
    const prev = byId.get(m.id);
    byId.set(m.id, prev ? { ...prev, ...m } : m);
  }
  return Array.from(byId.values()).sort((a, b) => {
    const ta = a.createdAt ? Date.parse(a.createdAt) : 0;
    const tb = b.createdAt ? Date.parse(b.createdAt) : 0;
    if (ta !== tb) return ta - tb;
    return a.id - b.id;
  });
}
