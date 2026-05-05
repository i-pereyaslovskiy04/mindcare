import { useState, useCallback } from 'react';
import Icon from '../../components/Icon';
import styles from './ChatWindow.module.css';

export default function MessageInput({ onSend }) {
  const [text, setText] = useState('');

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setText('');
  }, [text, onSend]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={styles.inputRow}>
      <input
        type="text"
        className={styles.input}
        placeholder="Напишите сообщение…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button
        className={styles.sendBtn}
        onClick={handleSend}
        disabled={!text.trim()}
        aria-label="Отправить"
      >
        <Icon name="send" size={14} />
        Отправить
      </button>
    </div>
  );
}
