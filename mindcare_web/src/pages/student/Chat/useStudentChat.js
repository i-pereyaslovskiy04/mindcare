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

const POLL_ACTIVE_MS = 8000;            // новые сообщения в активном диалоге
const POLL_NO_CONVERSATION_MS = 30000;  // ожидание назначения психолога
const HISTORY_LIMIT = 100;
const SNAPSHOT_LIMIT = 50;              // снапшот для live refresh (read_at + новые)

/** Достаёт человекочитаемый текст ошибки; raw HTTP-статусы заменяет fallback'ом. */
function errText(e, fallback) {
  const m = e?.message;
  if (typeof m === 'string' && m && !m.includes('[object') && !/^HTTP \d+$/.test(m)) {
    return m;
  }
  return fallback;
}

export function useStudentChat() {
  const [conversation, setConversation] = useState(null);
  const [messages, setMessages]         = useState([]);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState(null);
  const [sending, setSending]           = useState(false);
  const [sendError, setSendError]       = useState(null);

  const lastIdRef   = useRef(0);
  const pollBusyRef = useRef(false);

  const markReadSafe = useCallback(() => {
    // Не критично при сбое: непрочитанные пометятся при следующем открытии/poll.
    markMyConversationRead()
      .then(() => {
        setConversation((prev) => (prev ? { ...prev, unread_count: 0 } : prev));
        notifyMessagesUpdated();   // мгновенно гасим badge в меню
      })
      .catch(() => {});
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { conversation: conv } = await getMyConversation();
      setConversation(conv);
      if (conv) {
        const { items } = await getMyConversationMessages({ limit: HISTORY_LIMIT });
        setMessages(items.map(mapMessage));
        lastIdRef.current = items.length ? items[items.length - 1].id : 0;
        if (items.some((m) => !m.is_mine && !m.read_at)) markReadSafe();
      } else {
        setMessages([]);
        lastIdRef.current = 0;
      }
    } catch (e) {
      setError(errText(e, 'Не удалось загрузить чат. Попробуйте ещё раз.'));
    } finally {
      setLoading(false);
    }
  }, [markReadSafe]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const pollNew = useCallback(async () => {
    if (pollBusyRef.current) return;
    pollBusyRef.current = true;
    try {
      // Снапшот последних сообщений + merge по id: подхватывает новые И обновляет
      // read_at уже загруженных (after=<id> этого бы не дал → ✓→✓✓ без F5).
      const { items } = await getMyConversationMessages({ limit: SNAPSHOT_LIMIT });
      const mapped = items.map(mapMessage);
      if (mapped.length) {
        const lastId = mapped[mapped.length - 1].id;
        if (lastId > lastIdRef.current) lastIdRef.current = lastId;
      }
      setMessages((prev) => mergeMessages(prev, mapped));
      if (mapped.some((m) => !m.mine && !m.readAt)) markReadSafe();
    } catch {
      // Разовая сетевая ошибка poll'а не должна показывать баннер — повтор через интервал.
    } finally {
      pollBusyRef.current = false;
    }
  }, [markReadSafe]);

  const hasConversation = Boolean(conversation);
  const isActive = conversation?.engagement_status === 'active';

  useEffect(() => {
    if (loading || error) return undefined;
    if (!hasConversation) {
      // Психолог не назначен: редкий poll беседы, чтобы чат появился после назначения.
      const t = setInterval(() => {
        getMyConversation()
          .then(({ conversation: conv }) => {
            if (conv) loadAll();
          })
          .catch(() => {});
      }, POLL_NO_CONVERSATION_MS);
      return () => clearInterval(t);
    }
    // Закрытый диалог read-only: новых сообщений не будет, poll не нужен.
    if (!isActive) return undefined;
    const t = setInterval(pollNew, POLL_ACTIVE_MS);
    return () => clearInterval(t);
  }, [loading, error, hasConversation, isActive, pollNew, loadAll]);

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

  return { conversation, messages, loading, error, sending, sendError, send, refetch: loadAll };
}
