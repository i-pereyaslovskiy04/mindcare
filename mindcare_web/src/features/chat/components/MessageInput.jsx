import { useState, useEffect, useCallback } from 'react';
import Icon from '../../../components/Icon/Icon';
import styles from './ChatWindow.module.css';

const MAX_LENGTH = 10000; // лимит backend-валидации ChatMessageCreate/Edit

/**
 * Composer. Два режима (Stage 31x):
 *   - обычная отправка: submit → onSend(text);
 *   - редактирование: проп `editing` = { uuid, text } непустой → submit →
 *     onSubmitEdit(text); над input — панель «Редактирование сообщения» +
 *     «Отменить»; Escape отменяет (desktop). После успеха родитель сбрасывает
 *     `editing` в null, что очищает input.
 */
export default function MessageInput({
  onSend,
  sending = false,
  editing = null,
  onSubmitEdit = null,
  onCancelEdit = null,
}) {
  const [text, setText] = useState('');
  const isEditing = Boolean(editing);

  // Вход/выход из edit-mode: подставить текст редактируемого сообщения либо очистить.
  useEffect(() => {
    setText(editing ? editing.text : '');
  }, [editing]);

  const handleSubmit = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    if (isEditing) {
      const ok = await onSubmitEdit(trimmed);
      // При успехе родитель сбросит editing→null (useEffect очистит input).
      // При ошибке текст сохраняем, чтобы правка не потерялась.
      if (ok === false) return;
    } else {
      const ok = await onSend(trimmed);
      if (ok !== false) setText('');
    }
  }, [text, sending, isEditing, onSend, onSubmitEdit]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === 'Escape' && isEditing && onCancelEdit) {
      e.preventDefault();
      onCancelEdit();
    }
  };

  return (
    <div className={styles.composer}>
      {isEditing && (
        <div className={styles.editBanner}>
          <Icon name="edit" size={13} aria-hidden="true" />
          <span className={styles.editBannerLabel}>Редактирование сообщения</span>
          <button
            type="button"
            className={styles.editCancel}
            onClick={onCancelEdit}
          >
            Отменить
          </button>
        </div>
      )}
      <div className={styles.inputRow}>
        <input
          type="text"
          className={styles.input}
          placeholder={isEditing ? 'Измените сообщение…' : 'Напишите сообщение…'}
          value={text}
          maxLength={MAX_LENGTH}
          disabled={sending}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          type="button"
          className={styles.sendBtn}
          onClick={handleSubmit}
          disabled={!text.trim() || sending}
          aria-label={isEditing ? 'Сохранить' : 'Отправить'}
        >
          <Icon name={isEditing ? 'edit' : 'send'} size={14} />
          <span className={styles.sendLabel}>
            {isEditing ? (sending ? 'Сохранение…' : 'Сохранить') : sending ? 'Отправка…' : 'Отправить'}
          </span>
        </button>
      </div>
    </div>
  );
}
