import { Fragment, useEffect, useRef } from 'react';
import MessageItem from './MessageItem';
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

export default function MessageList({ messages, contact }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  let prevLabel = null;

  return (
    <div className={styles.messages}>
      {messages.length === 0 && (
        <div className={styles.threadEmpty}>Сообщений пока нет.</div>
      )}
      {messages.map((msg) => {
        const label = msg.createdAt ? dayLabel(msg.createdAt) : null;
        const showSep = label && label !== prevLabel;
        if (label) prevLabel = label;
        return (
          <Fragment key={msg.id}>
            {showSep && <div className={styles.dateSep}>{label}</div>}
            <MessageItem message={msg} contactInitials={contact.initials} />
          </Fragment>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
