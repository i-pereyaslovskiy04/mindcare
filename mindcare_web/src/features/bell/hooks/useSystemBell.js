import { useCallback, useEffect, useRef, useState } from 'react';
import { getSystemConversation, getSystemMessages } from '../../../api/chat.api';
import { subscribeMessagesUpdated } from '../../chat/lib/messagesEvents';
import { BELL_LIMIT, pickUnread } from '../lib/bellView';

const POLL_MS = 30000;

/**
 * Данные колокольчика — только чтение системной беседы, без своего
 * read/unread-состояния и без mark-read.
 *
 * unreadCount — unread_count системной беседы: опрос раз в 30 с и мгновенно по
 * messagesEvents (Messenger шлёт его после mark-read). До первого ответа и при
 * ошибке — null: badge не показывается. Это единственный опрос системной
 * беседы на уровне layout — useMessagesBadge её больше не запрашивает.
 *
 * loadItems — до BELL_LIMIT непрочитанных (вызывается при открытии панели);
 * ответ устаревшего запроса (панель закрыли, начат новый) отбрасывается.
 */
export function useSystemBell(enabled) {
  const [unreadCount, setUnreadCount] = useState(null);
  const [items, setItems] = useState([]);
  const [itemsStatus, setItemsStatus] = useState('idle'); // idle | loading | ready | error

  const requestRef = useRef(0);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
      requestRef.current += 1;
    };
  }, []);

  useEffect(() => {
    if (!enabled) {
      setUnreadCount(null);
      return undefined;
    }
    let alive = true;

    async function tick() {
      try {
        const { conversation } = await getSystemConversation();
        if (alive) setUnreadCount(conversation?.unread_count || 0);
      } catch {
        if (alive) setUnreadCount(null);
      }
    }

    tick();
    const t = setInterval(tick, POLL_MS);
    const unsub = subscribeMessagesUpdated(tick);
    return () => {
      alive = false;
      clearInterval(t);
      unsub();
    };
  }, [enabled]);

  const loadItems = useCallback(async () => {
    requestRef.current += 1;
    const request = requestRef.current;
    setItemsStatus('loading');
    try {
      const { items: raw } = await getSystemMessages({ limit: BELL_LIMIT });
      if (!aliveRef.current || request !== requestRef.current) return;
      setItems(pickUnread(raw, BELL_LIMIT));
      setItemsStatus('ready');
    } catch {
      if (!aliveRef.current || request !== requestRef.current) return;
      setItems([]);
      setItemsStatus('error');
    }
  }, []);

  /** Панель закрыта: незавершённый запрос не применяется, список сброшен. */
  const resetItems = useCallback(() => {
    requestRef.current += 1;
    setItems([]);
    setItemsStatus('idle');
  }, []);

  return { unreadCount, items, itemsStatus, loadItems, resetItems };
}
