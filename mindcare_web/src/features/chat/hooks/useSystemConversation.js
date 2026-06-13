import { useCallback, useRef, useState } from 'react';
import {
  getSystemConversation,
  getSystemMessages,
  markSystemConversationRead,
} from '../../../api/chat.api';
import { mapApiMessage } from '../lib/messageShape';

const HISTORY_LIMIT = 100;

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
      markSystemConversationRead().catch(() => {});
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
      const { items } = await getSystemMessages({ after: lastIdRef.current });
      if (items.length) {
        const lastId = items[items.length - 1].id;
        if (lastId > lastIdRef.current) lastIdRef.current = lastId;
        setMessages((prev) => {
          const known = new Set(prev.map((m) => m.id));
          const fresh = items.filter((m) => !known.has(m.id)).map(mapApiMessage);
          return fresh.length ? [...prev, ...fresh] : prev;
        });
        markSystemConversationRead().catch(() => {});
      }
    } catch {
      // разовый сетевой сбой poll'а — без баннера, повтор по интервалу
    } finally {
      pollBusyRef.current = false;
    }
  }, []);

  return { conversation, messages, loading, error, refreshMeta, open, close, pollNew };
}
