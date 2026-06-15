import { useState, useCallback } from 'react';
import Icon from '../../../components/Icon/Icon';
import styles from './ChatWindow.module.css';

const MAX_LENGTH = 10000; // лимит backend-валидации ChatMessageCreate

export default function MessageInput({ onSend, sending = false }) {
  const [text, setText] = useState('');

  const handleSend = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    const ok = await onSend(trimmed);
    // При ошибке отправки текст сохраняется, чтобы пользователь не потерял сообщение.
    if (ok !== false) setText('');
  }, [text, sending, onSend]);

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
        maxLength={MAX_LENGTH}
        disabled={sending}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button
        type="button"
        className={styles.sendBtn}
        onClick={handleSend}
        disabled={!text.trim() || sending}
        aria-label="Отправить"
      >
        <Icon name="send" size={14} />
        {sending ? 'Отправка…' : 'Отправить'}
      </button>
    </div>
  );
}
