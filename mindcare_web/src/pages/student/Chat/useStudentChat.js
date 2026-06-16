import { useCallback, useEffect, useRef, useState } from 'react';
import {
  deleteStudentMessage,
  editStudentMessage,
  getStudentConversations,
  getStudentConversationMessages,
  markStudentConversationRead,
  sendStudentConversationMessage,
} from '../../../api/chat.api';
import {
  mapApiMessage as mapMessage,
  mergeMessages,
} from '../../../features/chat/lib/messageShape';
import { notifyMessagesUpdated } from '../../../features/chat/lib/messagesEvents';

const POLL_MESSAGES_MS = 8000;   // новые сообщения выбранной активной беседы
const POLL_LIST_MS = 30000;      // обновление unread_count / появление новых бесед
const LIST_PAGE_SIZE = 100;
const HISTORY_LIMIT = 100;
const SNAPSHOT_LIMIT = 50;       // снапшот для live refresh (read_at + новые)

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

/**
 * Диалоги студента (Stage 31t — единая с психологом list-модель).
 *
 * Список бесед (active + non-empty inactive) с психологами; выбор по uuid;
 * чтение/отправка/read по conversation uuid. VK-like: вход НЕ открывает диалог
 * и НЕ помечает прочитанным — open/mark-read только по явному клику.
 */
export function useStudentChat() {
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
    markStudentConversationRead(uuid)
      .then(notifyMessagesUpdated)   // мгновенно гасим badge в меню
      .catch(() => {});
  }, []);

  const loadList = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setListLoading(true);
      setListError(null);
    }
    try {
      const data = await getStudentConversations({ page: 1, size: LIST_PAGE_SIZE });
      setConversations(
        data.items.map((c) =>
          c.uuid === selectedRef.current ? { ...c, unread_count: 0 } : c,
        ),
      );
      return data.items;
    } catch (e) {
      if (!silent) setListError(errText(e, 'Не удалось загрузить список диалогов.'));
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
        const { items } = await getStudentConversationMessages(uuid, {
          limit: HISTORY_LIMIT,
        });
        if (selectedRef.current !== uuid) return;
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

  const deselect = useCallback(() => {
    selectedRef.current = null;
    setSelectedUuid(null);
  }, []);

  // Первичная загрузка списка. VK-like: НЕ выбираем диалог автоматически.
  useEffect(() => {
    loadList();
  }, [loadList]);

  const pollNew = useCallback(async () => {
    const uuid = selectedRef.current;
    if (!uuid || pollBusyRef.current) return;
    pollBusyRef.current = true;
    try {
      const { items } = await getStudentConversationMessages(uuid, {
        limit: SNAPSHOT_LIMIT,
      });
      if (selectedRef.current !== uuid) return;
      const mapped = items.map(mapMessage);
      if (mapped.length) {
        const lastId = mapped[mapped.length - 1].id;
        if (lastId > lastIdRef.current) lastIdRef.current = lastId;
      }
      setMessages((prev) => mergeMessages(prev, mapped));
      if (mapped.some((m) => !m.mine && !m.readAt)) markReadSafe(uuid);
    } catch {
      // Разовая сетевая ошибка poll'а — без баннера, повтор по интервалу.
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

  // Редкий polling списка: unread других бесед и появление нового психолога.
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
      const msg = await sendStudentConversationMessage(uuid, text);
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
        // Engagement закрылся во время диалога: тихо обновляем список (статус/closed-state).
        if (e?.status === 409) loadList({ silent: true });
      }
      return false;
    } finally {
      setSending(false);
    }
  }, [loadList]);

  // Редактирование своего сообщения (Stage 31x): PATCH → точечная замена по uuid,
  // порядок сообщений сохраняется (createdAt не меняется). Без полной перезагрузки.
  const editMessage = useCallback(async (messageUuid, text) => {
    const uuid = selectedRef.current;
    if (!uuid || !messageUuid) return false;
    setSending(true);
    setSendError(null);
    try {
      const msg = await editStudentMessage(uuid, messageUuid, text);
      if (selectedRef.current === uuid) {
        const mapped = mapMessage(msg);
        setMessages((prev) => prev.map((m) => (m.uuid === mapped.uuid ? mapped : m)));
      }
      return true;
    } catch (e) {
      if (selectedRef.current === uuid) {
        setSendError(errText(e, 'Не удалось изменить сообщение. Попробуйте ещё раз.'));
        if (e?.status === 409) loadList({ silent: true });
      }
      return false;
    } finally {
      setSending(false);
    }
  }, [loadList]);

  // Удаление своего сообщения (Stage 31y): DELETE → точечная замена по uuid на
  // deleted-плейсхолдер (порядок и createdAt сохраняются). Без перезагрузки.
  const deleteMessage = useCallback(async (messageUuid) => {
    const uuid = selectedRef.current;
    if (!uuid || !messageUuid) return false;
    setSendError(null);
    try {
      const msg = await deleteStudentMessage(uuid, messageUuid);
      if (selectedRef.current === uuid) {
        const mapped = mapMessage(msg);
        setMessages((prev) => prev.map((m) => (m.uuid === mapped.uuid ? mapped : m)));
      }
      return true;
    } catch (e) {
      if (selectedRef.current === uuid) {
        setSendError(errText(e, 'Не удалось удалить сообщение. Попробуйте ещё раз.'));
        if (e?.status === 409) loadList({ silent: true });
      }
      return false;
    }
  }, [loadList]);

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
