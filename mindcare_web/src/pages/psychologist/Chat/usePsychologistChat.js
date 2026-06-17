import { useCallback, useEffect, useRef, useState } from 'react';
import {
  deletePsychologistMessage,
  editPsychologistMessage,
  getPsychologistConversation,
  getPsychologistConversationMessages,
  getPsychologistConversations,
  markPsychologistConversationRead,
  sendPsychologistConversationMessage,
} from '../../../api/chat.api';
import {
  mapApiMessage as mapMessage,
  reconcileMessagesSnapshot,
} from '../../../features/chat/lib/messageShape';
import { notifyMessagesUpdated } from '../../../features/chat/lib/messagesEvents';
import {
  HISTORY_LIMIT,
  LIST_PAGE_SIZE,
  POLL_LIST_MS,
  POLL_MESSAGES_MS,
  SNAPSHOT_LIMIT,
  errText,
} from '../../../features/chat/lib/chatHookUtils';

export function usePsychologistChat() {
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
    markPsychologistConversationRead(uuid)
      .then(notifyMessagesUpdated)   // мгновенно гасим badge в меню
      .catch(() => {});
  }, []);

  const loadList = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setListLoading(true);
      setListError(null);
    }
    try {
      const data = await getPsychologistConversations({ page: 1, size: LIST_PAGE_SIZE });
      // Открытая беседа читается сразу, поэтому её серверный unread гасим локально.
      setConversations(
        data.items.map((c) =>
          c.uuid === selectedRef.current ? { ...c, unread_count: 0 } : c,
        ),
      );
      return data.items;
    } catch (e) {
      if (!silent) setListError(errText(e, 'Не удалось загрузить список бесед.'));
      return null;
    } finally {
      if (!silent) setListLoading(false);
    }
  }, []);

  const loadMessages = useCallback(
    async (uuid) => {
      setMessagesLoading(true);
      setMessagesError(null);
      setSendError(null);
      setMessages([]);
      lastIdRef.current = 0;
      try {
        const { items } = await getPsychologistConversationMessages(uuid, {
          limit: HISTORY_LIMIT,
        });
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
    [markReadSafe],
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

  // Снять выбор беседы (mobile back к списку). Не трогает unread/mark-read:
  // прочитанные при открытии сообщения остаются прочитанными.
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
      // и удаление из локального state сообщений, удалённых собеседником.
      const { items } = await getPsychologistConversationMessages(uuid, {
        limit: SNAPSHOT_LIMIT,
      });
      if (selectedRef.current !== uuid) return;
      const mapped = items.map(mapMessage);
      if (mapped.length) {
        const lastId = mapped[mapped.length - 1].id;
        if (lastId > lastIdRef.current) lastIdRef.current = lastId;
      }
      setMessages((prev) => reconcileMessagesSnapshot(prev, mapped, knownMaxId));
      if (mapped.some((m) => !m.mine && !m.readAt)) markReadSafe(uuid);
    } catch {
      // Разовая сетевая ошибка poll'а не должна показывать баннер — повтор через интервал.
    } finally {
      pollBusyRef.current = false;
    }
  }, [markReadSafe]);

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
      const msg = await sendPsychologistConversationMessage(uuid, text);
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
        if (e?.status === 409) {
          // Engagement закрылся во время диалога: подтягиваем статус, UI уходит в closed-state.
          getPsychologistConversation(uuid)
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
        }
      }
      return false;
    } finally {
      setSending(false);
    }
  }, []);

  // Редактирование своего сообщения (Stage 31x): PATCH → точечная замена по uuid,
  // порядок сообщений сохраняется (createdAt не меняется). Без полной перезагрузки.
  const editMessage = useCallback(async (messageUuid, text) => {
    const uuid = selectedRef.current;
    if (!uuid || !messageUuid) return false;
    setSending(true);
    setSendError(null);
    try {
      const msg = await editPsychologistMessage(uuid, messageUuid, text);
      if (selectedRef.current === uuid) {
        const mapped = mapMessage(msg);
        setMessages((prev) => prev.map((m) => (m.uuid === mapped.uuid ? mapped : m)));
      }
      return true;
    } catch (e) {
      if (selectedRef.current === uuid) {
        setSendError(errText(e, 'Не удалось изменить сообщение. Попробуйте ещё раз.'));
        if (e?.status === 409) {
          getPsychologistConversation(uuid)
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
        }
      }
      return false;
    } finally {
      setSending(false);
    }
  }, []);

  // Удаление своего сообщения (Stage 31y-hotfix): DELETE → сообщение убирается
  // из ленты (без плейсхолдера). Порядок оставшихся сообщений сохраняется.
  const deleteMessage = useCallback(async (messageUuid) => {
    const uuid = selectedRef.current;
    if (!uuid || !messageUuid) return false;
    setSendError(null);
    try {
      await deletePsychologistMessage(uuid, messageUuid);
      if (selectedRef.current === uuid) {
        setMessages((prev) => prev.filter((m) => m.uuid !== messageUuid));
      }
      return true;
    } catch (e) {
      if (selectedRef.current === uuid) {
        setSendError(errText(e, 'Не удалось удалить сообщение. Попробуйте ещё раз.'));
      }
      return false;
    }
  }, []);

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
