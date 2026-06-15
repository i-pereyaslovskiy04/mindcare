import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getMyConversation,
  getMyConversationMessages,
  markMyConversationRead,
  sendMyConversationMessage,
} from '../../../api/chat.api';
import {
  mapApiMessage as mapMessage,
  mergeMessages,
} from '../../../features/chat/lib/messageShape';
import { notifyMessagesUpdated } from '../../../features/chat/lib/messagesEvents';

const META_POLL_MS = 30000;   // обновление unread/назначения психолога в списке
const HISTORY_LIMIT = 100;
const SNAPSHOT_LIMIT = 50;    // снапшот для live refresh (read_at + новые)

/** Достаёт человекочитаемый текст ошибки; raw HTTP-статусы заменяет fallback'ом. */
function errText(e, fallback) {
  const m = e?.message;
  if (typeof m === 'string' && m && !m.includes('[object') && !/^HTTP \d+$/.test(m)) {
    return m;
  }
  return fallback;
}

/**
 * Диалог студента с психологом.
 *
 * VK-like: вход в раздел НЕ открывает диалог и НЕ помечает прочитанным.
 *   - refreshMeta — только метаданные беседы (имя/статус/unread) для списка,
 *     без сообщений и без mark-read; крутится на интервале;
 *   - open()   — явное открытие: грузит сообщения + mark-read (вызывает страница
 *     по клику пользователя);
 *   - pollNew  — snapshot+merge живого обновления открытого диалога;
 *   - close()  — уход с диалога.
 */
export function useStudentChat() {
  const [conversation, setConversation]       = useState(null);
  const [messages, setMessages]               = useState([]);
  const [metaLoading, setMetaLoading]         = useState(true);
  const [metaError, setMetaError]             = useState(null);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messagesError, setMessagesError]     = useState(null);
  const [sending, setSending]                 = useState(false);
  const [sendError, setSendError]             = useState(null);

  const lastIdRef   = useRef(0);
  const openedRef   = useRef(false);
  const pollBusyRef = useRef(false);

  const markReadSafe = useCallback(() => {
    markMyConversationRead()
      .then(() => {
        setConversation((prev) => (prev ? { ...prev, unread_count: 0 } : prev));
        notifyMessagesUpdated();   // мгновенно гасим badge в меню
      })
      .catch(() => {});
  }, []);

  // Только метаданные: НЕ грузит сообщения и НЕ помечает прочитанным.
  const refreshMeta = useCallback(async () => {
    try {
      const { conversation: conv } = await getMyConversation();
      setConversation((prev) => {
        // Если диалог открыт — его unread уже погашен локально, не воскрешаем.
        if (openedRef.current && conv) return { ...conv, unread_count: 0 };
        return conv;
      });
      setMetaError(null);
      return conv;
    } catch (e) {
      setMetaError(errText(e, 'Не удалось загрузить чат. Попробуйте ещё раз.'));
      return null;
    } finally {
      setMetaLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshMeta();
    const t = setInterval(refreshMeta, META_POLL_MS);
    return () => clearInterval(t);
  }, [refreshMeta]);

  // Явное открытие диалога: грузит историю и помечает прочитанным.
  const open = useCallback(async () => {
    openedRef.current = true;
    setMessagesLoading(true);
    setMessagesError(null);
    setSendError(null);
    setMessages([]);
    lastIdRef.current = 0;
    try {
      const { items } = await getMyConversationMessages({ limit: HISTORY_LIMIT });
      if (!openedRef.current) return;
      setMessages(items.map(mapMessage));
      lastIdRef.current = items.length ? items[items.length - 1].id : 0;
      if (items.some((m) => !m.is_mine && !m.read_at)) markReadSafe();
    } catch (e) {
      if (openedRef.current) {
        setMessagesError(errText(e, 'Не удалось загрузить сообщения.'));
      }
    } finally {
      setMessagesLoading(false);
    }
  }, [markReadSafe]);

  const close = useCallback(() => {
    openedRef.current = false;
    setMessages([]);
    lastIdRef.current = 0;
  }, []);

  const pollNew = useCallback(async () => {
    if (!openedRef.current || pollBusyRef.current) return;
    pollBusyRef.current = true;
    try {
      const { items } = await getMyConversationMessages({ limit: SNAPSHOT_LIMIT });
      if (!openedRef.current) return;
      const mapped = items.map(mapMessage);
      if (mapped.length) {
        const lastId = mapped[mapped.length - 1].id;
        if (lastId > lastIdRef.current) lastIdRef.current = lastId;
      }
      setMessages((prev) => mergeMessages(prev, mapped));
      if (mapped.some((m) => !m.mine && !m.readAt)) markReadSafe();
    } catch {
      // Разовая сетевая ошибка poll'а — без баннера, повтор по интервалу.
    } finally {
      pollBusyRef.current = false;
    }
  }, [markReadSafe]);

  const send = useCallback(async (text) => {
    setSending(true);
    setSendError(null);
    try {
      const msg = await sendMyConversationMessage(text);
      if (msg.id > lastIdRef.current) lastIdRef.current = msg.id;
      setMessages((prev) =>
        prev.some((m) => m.id === msg.id) ? prev : [...prev, mapMessage(msg)],
      );
      return true;
    } catch (e) {
      setSendError(errText(e, 'Не удалось отправить сообщение. Попробуйте ещё раз.'));
      return false;
    } finally {
      setSending(false);
    }
  }, []);

  return {
    conversation, messages,
    metaLoading, metaError,
    messagesLoading, messagesError,
    sending, sendError,
    refreshMeta, open, close, pollNew, send,
  };
}
