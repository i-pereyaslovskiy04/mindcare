import { useEffect, useRef } from 'react';
import MessageItem from './MessageItem';
import styles from './ChatWindow.module.css';

export default function MessageList({ messages, contact }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className={styles.messages}>
      <div className={styles.dateSep}>Сегодня</div>
      {messages.map((msg) => (
        <MessageItem key={msg.id} message={msg} contactInitials={contact.initials} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
