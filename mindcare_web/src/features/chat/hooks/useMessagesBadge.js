import { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import {
  getMyConversation,
  getPsychologistConversations,
  getSystemConversation,
} from '../../../api/chat.api';
import { subscribeMessagesUpdated } from '../lib/messagesEvents';

const POLL_MS = 30000;

/**
 * Badge раздела «Сообщения» = ЧИСЛО ДИАЛОГОВ с unread_count > 0
 * (system-беседа и engagement-беседа считаются раздельно), НЕ сумма сообщений.
 *
 * Лёгкий self-poll (30s) на уровне layout. Возвращает число или 0.
 * Источник engagement-части зависит от роли; system — у всех ролей.
 */
export function useMessagesBadge() {
  const { user } = useAuth();
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!user || (user.role !== 'student' && user.role !== 'psychologist')) {
      setCount(0);
      return undefined;
    }

    let alive = true;

    async function tick() {
      let dialogs = 0;
      try {
        if (user.role === 'student') {
          const { conversation } = await getMyConversation();
          if (conversation && conversation.unread_count > 0) dialogs += 1;
        } else {
          const data = await getPsychologistConversations({ page: 1, size: 100 });
          dialogs += data.items.filter((c) => c.unread_count > 0).length;
        }
      } catch {
        /* сетевой сбой — оставляем прежнее значение */
      }
      try {
        const { conversation: sys } = await getSystemConversation();
        if (sys && sys.unread_count > 0) dialogs += 1;
      } catch {
        /* ignore */
      }
      if (alive) setCount(dialogs);
    }

    tick();
    const t = setInterval(tick, POLL_MS);
    // Мгновенный refresh при mark-read/send/новых — не ждём 30-секундный тик.
    const unsub = subscribeMessagesUpdated(tick);
    return () => {
      alive = false;
      clearInterval(t);
      unsub();
    };
  }, [user]);

  return count;
}
