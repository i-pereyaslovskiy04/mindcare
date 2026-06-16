import { Fragment, useEffect, useRef } from 'react';
import MessageItem from './MessageItem';
import { shouldShowAuthorHeader } from '../lib/messageShape';
import styles from './ChatWindow.module.css';

function dayLabel(iso) {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return 'Сегодня';
  if (d.toDateString() === yesterday.toDateString()) return 'Вчера';
  return d.toLocaleDateString('ru', { day: 'numeric', month: 'long' });
}

export default function MessageList({
  messages,
  contact,
  emptyText,
  manageable = false,
  onStartEdit = null,
  onRequestDelete = null,
}) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Удалённые сообщения скрыты из ленты (Stage 31y-hotfix): фильтруем до расчёта
  // author-header/date-сепараторов, чтобы они считались по видимым сообщениям.
  const visible = messages.filter((m) => !m.deleted);

  let prevLabel = null;

  return (
    <div className={styles.messages}>
      {visible.length === 0 && (
        <div className={styles.threadEmpty}>{emptyText || 'Сообщений пока нет.'}</div>
      )}
      {visible.map((msg, idx) => {
        const label = msg.createdAt ? dayLabel(msg.createdAt) : null;
        const showSep = label && label !== prevLabel;
        if (label) prevLabel = label;
        const showAuthorHeader = shouldShowAuthorHeader(visible, idx);
        // Подпись автора: «Вы» для своих, «ФИО · роль» для собеседника.
        const authorName = msg.mine ? 'Вы' : contact.name;
        const authorRole = msg.mine ? null : contact.authorRole || null;
        return (
          <Fragment key={msg.id}>
            {showSep && <div className={styles.dateSep}>{label}</div>}
            <MessageItem
              message={msg}
              contactInitials={contact.initials}
              showAuthorHeader={showAuthorHeader}
              authorName={authorName}
              authorRole={authorRole}
              manageable={manageable}
              onStartEdit={onStartEdit}
              onRequestDelete={onRequestDelete}
            />
          </Fragment>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
