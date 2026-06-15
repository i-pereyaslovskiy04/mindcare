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
    senderId: m.sender_id ?? null,
    time: formatTime(m.created_at),
    createdAt: m.created_at,
    readAt: m.read_at || null,
  };
}

/** Крупный перерыв между сообщениями одного автора → новый author header. */
const AUTHOR_HEADER_GAP_MS = 5 * 60 * 1000;

function sameDay(aIso, bIso) {
  if (!aIso || !bIso) return false;
  return new Date(aIso).toDateString() === new Date(bIso).toDateString();
}

/** Идентификатор автора для группировки (fallback на mine, если sender_id нет). */
function authorKey(m) {
  if (m.senderId != null) return `id:${m.senderId}`;
  return m.mine ? 'me' : 'peer';
}

/**
 * Нужно ли показывать author header (VK-style подпись отправителя) над
 * сообщением с индексом `index` в списке `messages`.
 *
 * Header показывается у ПЕРВОГО сообщения группы. Группа прерывается, если:
 *   - это первое сообщение в списке;
 *   - предыдущий элемент — system-сообщение (после служебного сепаратора);
 *   - сменилась календарная дата (после date-сепаратора в MessageList);
 *   - сменился отправитель;
 *   - большой перерыв во времени (≥ AUTHOR_HEADER_GAP_MS) у того же автора.
 *
 * Для system-сообщений header не показывается никогда (нет human-автора).
 */
export function shouldShowAuthorHeader(messages, index) {
  const msg = messages[index];
  if (!msg || msg.system) return false;
  if (index === 0) return true;
  const prev = messages[index - 1];
  if (prev.system) return true;
  if (!sameDay(prev.createdAt, msg.createdAt)) return true;
  if (authorKey(prev) !== authorKey(msg)) return true;
  const dt = Date.parse(msg.createdAt) - Date.parse(prev.createdAt);
  if (Number.isFinite(dt) && dt >= AUTHOR_HEADER_GAP_MS) return true;
  return false;
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
