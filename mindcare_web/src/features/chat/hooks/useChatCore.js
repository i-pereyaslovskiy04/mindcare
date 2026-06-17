import { useCallback, useEffect, useRef, useState } from 'react';
import {
  mapApiMessage as mapMessage,
  reconcileMessagesSnapshot,
} from '../lib/messageShape';
import { notifyMessagesUpdated } from '../lib/messagesEvents';
import {
  HISTORY_LIMIT,
  LIST_PAGE_SIZE,
  POLL_LIST_MS,
  POLL_MESSAGES_MS,
  SNAPSHOT_LIMIT,
  errText,
} from '../lib/chatHookUtils';

/**
 * Shared chat core для student/psychologist chat-хуков.
 *
 * Принимает role-specific API adapter:
 *   listConversations(params)         — список диалогов
 *   getMessages(uuid, params)         — сообщения беседы
 *   sendMessage(uuid, text)           — отправить
 *   editMessage(uuid, msgUuid, text)  — редактировать
 *   deleteMessage(uuid, msgUuid)      — удалить
 *   markConversationRead(uuid)        — mark-read
 *   getConversation(uuid) | null      — одиночная беседа для точечного 409-refresh;
 *                                       null → fallback на silent loadList (student)
 *   listErrorMessage                  — copy при ошибке загрузки списка
 *
 * Return shape идентичен useStudentChat / usePsychologistChat до refactor.
 */
export function useChatCore({
  listConversations,
  getMessages,
  sendMessage,
  editMessage: apiEditMessage,
  deleteMessage: apiDeleteMessage,
  markConversationRead,
  getConversation,
  listErrorMessage,
}) {
  const [conversations, setConversations]     = useState([]);
  const [listLoading, setListLoading]         = useState(true);
  const [listError, setListError]             = useState(null);
  const [selectedUuid, setSelectedUuid]       = useState(null);
  const [messages, setMessages]               = useState([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messagesError, setMessagesError]     = useState(null);
  const [sending, setSending]                 = useState(false);
  const [sendError, setSendError]             = useState(null);

  const selectedRef = useRef(null);  // guard от гонок при переключении беседы
  const lastIdRef   = useRef(0);
  const pollBusyRef = useRef(false);

  const markReadSafe = useCallback((uuid) => {
    // Не критично при сбое: непрочитанные пометятся при следующем открытии/poll.
    markConversationRead(uuid)
      .then(notifyMessagesUpdated)   // мгновенно гасим badge в меню
      .catch(() => {});
  }, [markConversationRead]);

  const loadList = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setListLoading(true);
      setListError(null);
    }
    try {
      const data = await listConversations({ page: 1, size: LIST_PAGE_SIZE });
      // Открытая беседа читается сразу, поэтому её серверный unread гасим локально.
      setConversations(
        data.items.map((c) =>
          c.uuid === selectedRef.current ? { ...c, unread_count: 0 } : c,
        ),
      );
      return data.items;
    } catch (e) {
      if (!silent) setListError(errText(e, listErrorMessage));
      return null;
    } finally {
      if (!silent) setListLoading(false);
    }
  }, [listConversations, listErrorMessage]);

  // 409 Conflict: engagement закрылся во время диалога → обновить conversation в state.
  // getConversation != null (psychologist): точечный refresh одной беседы.
  // getConversation == null (student): fallback — silent reload всего списка.
  const refreshConversationAfterConflict = useCallback((uuid) => {
    if (!getConversation) {
      loadList({ silent: true });
      return;
    }
    getConversation(uuid)
      .then((conv) =>
        setConversations((prev) =>
          prev.map((c) =>
            c.uuid === uuid
              ? {
                  ...c,
                  engagement_status: conv.engagement_status,
                  last_message_at: conv.last_message_at,
                }
              : c,
          ),
        ),
      )
      .catch(() => {});
  }, [getConversation, loadList]);

  const loadMessages = useCallback(
    async (uuid) => {
      setMessagesLoading(true);
      setMessagesError(null);
      setSendError(null);
      setMessages([]);
      lastIdRef.current = 0;
      try {
        const { items } = await getMessages(uuid, { limit: HISTORY_LIMIT });
        if (selectedRef.current !== uuid) return; // беседу переключили во время загрузки
        setMessages(items.map(mapMessage));
        lastIdRef.current = items.length ? items[items.length - 1].id : 0;
        if (items.some((m) => !m.is_mine && !m.read_at)) markReadSafe(uuid);
        setConversations((prev) =>
          prev.map((c) => (c.uuid === uuid ? { ...c, unread_count: 0 } : c)),
        );
      } catch (e) {
        if (selectedRef.current !== uuid) return;
        setMessagesError(errText(e, 'Не удалось загрузить сообщения.'));
      } finally {
        if (selectedRef.current === uuid) setMessagesLoading(false);
      }
    },
    [getMessages, markReadSafe],
  );

  const selectConversation = useCallback(
    (uuid) => {
      if (selectedRef.current === uuid) return;
      selectedRef.current = uuid;
      setSelectedUuid(uuid);
      loadMessages(uuid);
    },
    [loadMessages],
  );

  const reloadMessages = useCallback(() => {
    if (selectedRef.current) loadMessages(selectedRef.current);
  }, [loadMessages]);

  // Снять выбор беседы (mobile back к списку). Не трогает unread/mark-read.
  const deselect = useCallback(() => {
    selectedRef.current = null;
    setSelectedUuid(null);
  }, []);

  // Первичная загрузка списка. VK-like: НЕ выбираем диалог автоматически —
  // открытие (и mark-read) только по явному клику пользователя.
  useEffect(() => {
    loadList();
  }, [loadList]);

  const pollNew = useCallback(async () => {
    const uuid = selectedRef.current;
    if (!uuid || pollBusyRef.current) return;
    pollBusyRef.current = true;
    // Фиксируем наибольший известный id ДО запроса: защита от race concurrent-send.
    const knownMaxId = lastIdRef.current;
    try {
      // Snapshot reconciliation: новые сообщения, обновление read_at/editedAt,
      // и удаление из локального state сообщений, soft-deleted на сервере.
      const { items } = await getMessages(uuid, { limit: SNAPSHOT_LIMIT });
      if (selectedRef.current !== uuid) return;
      const mapped = items.map(mapMessage);
      if (mapped.length) {
        const lastId = mapped[mapped.length - 1].id;
        if (lastId > lastIdRef.current) lastIdRef.current = lastId;
      }
      setMessages((prev) => reconcileMessagesSnapshot(prev, mapped, knownMaxId));
      if (mapped.some((m) => !m.mine && !m.readAt)) markReadSafe(uuid);
    } catch {
      // Разовая сетевая ошибка poll'а — без баннера, повтор по интервалу.
    } finally {
      pollBusyRef.current = false;
    }
  }, [getMessages, markReadSafe]);

  const selected = conversations.find((c) => c.uuid === selectedUuid) ?? null;
  const isActive = selected?.engagement_status === 'active';

  // Polling сообщений выбранной активной беседы (закрытая read-only — новых не будет).
  useEffect(() => {
    if (!selectedUuid || !isActive || messagesLoading || messagesError) return undefined;
    const t = setInterval(pollNew, POLL_MESSAGES_MS);
    return () => clearInterval(t);
  }, [selectedUuid, isActive, messagesLoading, messagesError, pollNew]);

  // Редкий polling списка: unread других бесед и появление новых клиентов.
  useEffect(() => {
    if (listLoading || listError) return undefined;
    const t = setInterval(() => loadList({ silent: true }), POLL_LIST_MS);
    return () => clearInterval(t);
  }, [listLoading, listError, loadList]);

  const send = useCallback(async (text) => {
    const uuid = selectedRef.current;
    if (!uuid) return false;
    setSending(true);
    setSendError(null);
    try {
      const msg = await sendMessage(uuid, text);
      if (selectedRef.current === uuid) {
        if (msg.id > lastIdRef.current) lastIdRef.current = msg.id;
        setMessages((prev) =>
          prev.some((m) => m.id === msg.id) ? prev : [...prev, mapMessage(msg)],
        );
      }
      return true;
    } catch (e) {
      if (selectedRef.current === uuid) {
        setSendError(errText(e, 'Не удалось отправить сообщение. Попробуйте ещё раз.'));
        if (e?.status === 409) refreshConversationAfterConflict(uuid);
      }
      return false;
    } finally {
      setSending(false);
    }
  }, [sendMessage, refreshConversationAfterConflict]);

  // PATCH → точечная замена по uuid, порядок сообщений сохраняется.
  const editMessage = useCallback(async (messageUuid, text) => {
    const uuid = selectedRef.current;
    if (!uuid || !messageUuid) return false;
    setSending(true);
    setSendError(null);
    try {
      const msg = await apiEditMessage(uuid, messageUuid, text);
      if (selectedRef.current === uuid) {
        const mapped = mapMessage(msg);
        setMessages((prev) => prev.map((m) => (m.uuid === mapped.uuid ? mapped : m)));
      }
      return true;
    } catch (e) {
      if (selectedRef.current === uuid) {
        setSendError(errText(e, 'Не удалось изменить сообщение. Попробуйте ещё раз.'));
        if (e?.status === 409) refreshConversationAfterConflict(uuid);
      }
      return false;
    } finally {
      setSending(false);
    }
  }, [apiEditMessage, refreshConversationAfterConflict]);

  // DELETE → убирает сообщение из ленты без плейсхолдера; только при успехе.
  const deleteMessage = useCallback(async (messageUuid) => {
    const uuid = selectedRef.current;
    if (!uuid || !messageUuid) return false;
    setSendError(null);
    try {
      await apiDeleteMessage(uuid, messageUuid);
      if (selectedRef.current === uuid) {
        setMessages((prev) => prev.filter((m) => m.uuid !== messageUuid));
      }
      return true;
    } catch (e) {
      if (selectedRef.current === uuid) {
        setSendError(errText(e, 'Не удалось удалить сообщение. Попробуйте ещё раз.'));
        if (e?.status === 409) refreshConversationAfterConflict(uuid);
      }
      return false;
    }
  }, [apiDeleteMessage, refreshConversationAfterConflict]);

  return {
    conversations,
    listLoading,
    listError,
    reloadList: loadList,
    selected,
    selectedUuid,
    selectConversation,
    deselect,
    messages,
    messagesLoading,
    messagesError,
    reloadMessages,
    sending,
    sendError,
    send,
    editMessage,
    deleteMessage,
  };
}
