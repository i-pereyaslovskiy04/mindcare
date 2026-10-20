import { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import {
  getStudentConversations,
  getPsychologistConversations,
} from '../../../api/chat.api';
import { subscribeMessagesUpdated } from '../lib/messagesEvents';

const POLL_MS = 30000;

/**
 * Badge раздела «Сообщения» = ЧИСЛО ЛИЧНЫХ ДИАЛОГОВ с unread_count > 0,
 * НЕ сумма сообщений. Системная беседа «Психология ДонГУ» сюда не входит:
 * её непрочитанные показывает колокольчик шапки (features/bell), одно событие
 * не считается дважды. Внутри Messenger у строки системной беседы её
 * собственный unread остаётся.
 *
 * Лёгкий self-poll (30s) на уровне layout. Возвращает число или 0.
 *
 * `role` — роль КАБИНЕТА (student/psychologist), в котором рендерится layout,
 * а не legacy `user.role`. Для multi-role пользователя это важно: студент-
 * психолог в /student видит student-диалоги, в /psychologist — psychologist.
 */
export function useMessagesBadge(role) {
  const { user } = useAuth();
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!user || (role !== 'student' && role !== 'psychologist')) {
      setCount(0);
      return undefined;
    }

    let alive = true;

    async function tick() {
      let dialogs = 0;
      try {
        if (role === 'student') {
          const data = await getStudentConversations({ page: 1, size: 100 });
          dialogs += data.items.filter((c) => c.unread_count > 0).length;
        } else {
          const data = await getPsychologistConversations({ page: 1, size: 100 });
          dialogs += data.items.filter((c) => c.unread_count > 0).length;
        }
      } catch {
        /* сетевой сбой — оставляем прежнее значение */
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
  }, [user, role]);

  return count;
}
