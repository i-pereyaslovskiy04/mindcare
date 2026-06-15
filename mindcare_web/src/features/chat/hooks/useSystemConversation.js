import { useCallback, useRef, useState } from 'react';
import {
  getSystemConversation,
  getSystemMessages,
  markSystemConversationRead,
} from '../../../api/chat.api';
import { mapApiMessage, mergeMessages } from '../lib/messageShape';
import { notifyMessagesUpdated } from '../lib/messagesEvents';

const HISTORY_LIMIT = 100;
const SNAPSHOT_LIMIT = 50;

/**
 * Read-only системная беседа текущего пользователя.
 *
 * Метаданные (unread/last_message_at) подтягиваются лёгким refreshMeta —
 * его дёргает общий polling страницы (отдельного интервала не заводим).
 * Сообщения грузятся при открытии (open) + помечаются прочитанными;
 * новые догружаются pollNew через after=<id> только когда беседа открыта.
 */
export function useSystemConversation() {
  const [conversation, setConversation] = useState(null);
  const [messages, setMessages]         = useState([]);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState(null);
  const [metaLoaded, setMetaLoaded]     = useState(false);  // первый refreshMeta завершён

  const lastIdRef = useRef(0);
  const openedRef = useRef(false);
  const pollBusyRef = useRef(false);

  const refreshMeta = useCallback(async () => {
    try {
      const { conversation: conv } = await getSystemConversation();
      setConversation((prev) => {
        // Если беседа открыта — её unread уже погашен локально, не воскрешаем.
        if (openedRef.current && conv) return { ...conv, unread_count: 0 };
        return conv;
      });
      return conv;
    } catch {
      return null;
    } finally {
      setMetaLoaded(true);
    }
  }, []);

  const open = useCallback(async () => {
    setLoading(true);
    setError(null);
    openedRef.current = true;
    try {
      const { items } = await getSystemMessages({ limit: HISTORY_LIMIT });
      setMessages(items.map(mapApiMessage));
      lastIdRef.current = items.length ? items[items.length - 1].id : 0;
      markSystemConversationRead().then(notifyMessagesUpdated).catch(() => {});
      setConversation((prev) => (prev ? { ...prev, unread_count: 0 } : prev));
    } catch (e) {
      const m = e?.message;
      setError(
        typeof m === 'string' && m && !/^HTTP \d+$/.test(m)
          ? m
          : 'Не удалось загрузить уведомления.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const close = useCallback(() => {
    openedRef.current = false;
  }, []);

  const pollNew = useCallback(async () => {
    if (!openedRef.current || pollBusyRef.current) return;
    pollBusyRef.current = true;
    try {
      const { items } = await getSystemMessages({ limit: SNAPSHOT_LIMIT });
      const mapped = items.map(mapApiMessage);
      if (mapped.length) {
        const lastId = mapped[mapped.length - 1].id;
        if (lastId > lastIdRef.current) lastIdRef.current = lastId;
      }
      setMessages((prev) => mergeMessages(prev, mapped));
      if (mapped.some((m) => !m.readAt)) {
        markSystemConversationRead().then(notifyMessagesUpdated).catch(() => {});
        setConversation((prev) => (prev ? { ...prev, unread_count: 0 } : prev));
      }
    } catch {
      // разовый сетевой сбой poll'а — без баннера, повтор по интервалу
    } finally {
      pollBusyRef.current = false;
    }
  }, []);

  return {
    conversation, messages, loading, error, metaLoaded,
    refreshMeta, open, close, pollNew,
  };
}
