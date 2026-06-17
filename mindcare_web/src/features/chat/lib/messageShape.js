/**
 * Единая UI-форма сообщения для всех chat-страниц (student/psychologist/system).
 *
 * Backend ChatMessageRead → { id, text, mine, system, time, createdAt, readAt }.
 *   mine   — рисуем справа («моё»), показываем read receipts;
 *   system — message_kind='system' (sender_role='system'): обычный incoming
 *            bubble с подписью «MindCare» вместо ФИО, без меню действий,
 *            без read receipts, не «моё».
 */

export function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
}

export function mapApiMessage(m) {
  return {
    id: m.id,
    uuid: m.uuid,
    text: m.content,
    mine: m.is_mine === true,
    system: m.sender_role === 'system',
    senderId: m.sender_id ?? null,
    time: formatTime(m.created_at),
    createdAt: m.created_at,
    readAt: m.read_at || null,
    editedAt: m.edited_at || null,
    deleted: m.is_deleted === true,
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
  if (m.system) return 'system';
  if (m.senderId != null) return `id:${m.senderId}`;
  return m.mine ? 'me' : 'peer';
}

/**
 * Нужно ли показывать author header (VK-style подпись отправителя) над
 * сообщением с индексом `index` в списке `messages`.
 *
 * Header показывается у ПЕРВОГО сообщения группы. Группа прерывается, если:
 *   - это первое сообщение в списке;
 *   - сменилась календарная дата (после date-сепаратора в MessageList);
 *   - сменился отправитель (включая переход human ↔ system — authorKey различает их);
 *   - большой перерыв во времени (≥ AUTHOR_HEADER_GAP_MS) у того же автора.
 *
 * System-сообщения получают header по той же логике, что и обычные —
 * подпись «MindCare» вместо ФИО собеседника (см. MessageList).
 */
export function shouldShowAuthorHeader(messages, index) {
  const msg = messages[index];
  if (!msg) return false;
  if (index === 0) return true;
  const prev = messages[index - 1];
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

/**
 * Snapshot reconciliation: синхронизирует локальный список с полным server snapshot'ом
 * и удаляет сообщения, которые backend больше не возвращает (soft-deleted).
 *
 * Безопасно ТОЛЬКО для polling с полным snapshot (не для partial/cursor pagination).
 * Snapshot «окно» определяется как [minSnapshotId, maxSnapshotId]:
 *   • id < minSnapshotId — история за пределами snapshot limit → сохраняется без изменений;
 *   • id > maxSnapshotId AND id > knownMaxId — отправлено параллельно с in-flight запросом
 *     (race), ещё не вошло в snapshot → сохраняется;
 *   • всё остальное, отсутствующее в snapshot → soft-deleted → удаляется.
 *
 * knownMaxId — наибольший id, известный до начала API-вызова (lastIdRef.current).
 * По умолчанию 0: все сообщения выше maxSnapshotId защищены — безопасный fallback
 * для пустого state. При реальном polling всегда передавать lastIdRef.current.
 *
 * Известное ограничение MVP: сообщения ниже snapshot window (id < minSnapshotId,
 * т.е. история старше SNAPSHOT_LIMIT) не reconcile-ятся — они были загружены через
 * HISTORY_LIMIT и выходят за пределы snapshot. Полная синхронизация только при
 * перезагрузке диалога.
 */
export function reconcileMessagesSnapshot(currentMessages, snapshotMessages, knownMaxId = 0) {
  if (!snapshotMessages || snapshotMessages.length === 0) return currentMessages;

  const snapshotById = new Map();
  for (const m of snapshotMessages) snapshotById.set(m.id, m);

  const ids = snapshotMessages.map((m) => m.id);
  const minId = Math.min(...ids);
  const maxId = Math.max(...ids);

  const result = new Map();

  for (const m of currentMessages) {
    if (m.id < minId) {
      // Ниже snapshot window (история за пределами limit) — сохраняем без изменений.
      result.set(m.id, m);
    } else if (m.id > maxId && m.id > knownMaxId) {
      // Выше snapshot window И новее, чем было известно до начала запроса —
      // отправлено параллельно с in-flight GET → сохраняем.
      result.set(m.id, m);
    }
    // id в [minId, maxId] не в snapshot: soft-deleted → пропускаем.
    // id > maxId но <= knownMaxId: было известно до запроса, не вернулось → deleted → пропускаем.
  }

  // Добавляем/обновляем все сообщения из snapshot (snapshot-данные приоритетнее).
  for (const m of snapshotMessages) {
    result.set(m.id, m);
  }

  return Array.from(result.values()).sort((a, b) => {
    const ta = a.createdAt ? Date.parse(a.createdAt) : 0;
    const tb = b.createdAt ? Date.parse(b.createdAt) : 0;
    if (ta !== tb) return ta - tb;
    return a.id - b.id;
  });
}
