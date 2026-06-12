import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getPsychologistConversation,
  getPsychologistConversationMessages,
  getPsychologistConversations,
  markPsychologistConversationRead,
  sendPsychologistConversationMessage,
} from '../../../api/chat.api';

const POLL_MESSAGES_MS = 8000;   // новые сообщения выбранной активной беседы
const POLL_LIST_MS = 30000;      // обновление unread_count / появление новых бесед
const LIST_PAGE_SIZE = 100;
const HISTORY_LIMIT = 100;

function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
}

/** Backend message → UI-форма, которую ждут MessageList/MessageItem. */
function mapMessage(m) {
  return {
    id: m.id,
    text: m.content,
    sender: m.is_mine ? 'me' : 'student',
    time: formatTime(m.created_at),
    createdAt: m.created_at,
  };
}

const STATUS_FALLBACK = {
  403: 'Нет доступа к этому чату',
  404: 'Диалог не найден или недоступен',
  409: 'Диалог закрыт',
  429: 'Слишком много сообщений. Попробуйте позже.',
};

/** Человекочитаемый текст ошибки; raw HTTP-статусы заменяются fallback'ом. */
function errText(e, fallback) {
  const m = e?.message;
  if (typeof m === 'string' && m && !m.includes('[object') && !/^HTTP \d+$/.test(m)) {
    return m;
  }
  return STATUS_FALLBACK[e?.status] || fallback;
}

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
    markPsychologistConversationRead(uuid).catch(() => {});
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

  // Первичная загрузка списка + автовыбор первой беседы.
  useEffect(() => {
    (async () => {
      const items = await loadList();
      if (items && items.length && !selectedRef.current) {
        selectConversation(items[0].uuid);
      }
    })();
  }, [loadList, selectConversation]);

  const pollNew = useCallback(async () => {
    const uuid = selectedRef.current;
    if (!uuid || pollBusyRef.current) return;
    pollBusyRef.current = true;
    try {
      const { items } = await getPsychologistConversationMessages(uuid, {
        after: lastIdRef.current,
      });
      if (selectedRef.current !== uuid) return;
      if (items.length) {
        const lastId = items[items.length - 1].id;
        if (lastId > lastIdRef.current) lastIdRef.current = lastId;
        setMessages((prev) => {
          const known = new Set(prev.map((m) => m.id));
          const fresh = items.filter((m) => !known.has(m.id)).map(mapMessage);
          return fresh.length ? [...prev, ...fresh] : prev;
        });
        if (items.some((m) => !m.is_mine)) markReadSafe(uuid);
      }
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

  return {
    conversations,
    listLoading,
    listError,
    reloadList: loadList,
    selected,
    selectedUuid,
    selectConversation,
    messages,
    messagesLoading,
    messagesError,
    reloadMessages,
    sending,
    sendError,
    send,
  };
}
