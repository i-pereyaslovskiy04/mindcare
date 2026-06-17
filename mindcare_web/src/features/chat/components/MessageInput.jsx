import { useState, useEffect, useCallback, useLayoutEffect, useRef } from 'react';
import Icon from '../../../components/Icon/Icon';
import styles from './ChatWindow.module.css';

const MAX_LENGTH = 10000; // лимит backend-валидации ChatMessageCreate/Edit
const FALLBACK_LINE_HEIGHT = 18;

function px(value) {
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : 0;
}

function getMaxHeightForLines(textarea, lines) {
  const cs = window.getComputedStyle(textarea);
  const fontSize = px(cs.fontSize) || 13.5;
  let lineHeight = px(cs.lineHeight) || Math.round(fontSize * 1.35) || FALLBACK_LINE_HEIGHT;
  if (lineHeight < fontSize) lineHeight *= fontSize;
  const verticalPadding = px(cs.paddingTop) + px(cs.paddingBottom);
  const verticalBorder = px(cs.borderTopWidth) + px(cs.borderBottomWidth);

  return (lineHeight * lines) + verticalPadding + verticalBorder;
}

function autosizeTextarea(textarea) {
  if (!textarea) return;

  const maxHeight = getMaxHeightForLines(textarea, 3);
  const minHeight = getMaxHeightForLines(textarea, 1);
  textarea.style.height = 'auto';
  const nextHeight = Math.min(textarea.scrollHeight || minHeight, maxHeight);

  textarea.style.height = `${nextHeight}px`;
  textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden';
}

function isTouchComposerMode() {
  if (typeof window === 'undefined') return false;
  if (typeof window.matchMedia === 'function') {
    return window.matchMedia('(hover: none) and (pointer: coarse)').matches;
  }
  return window.innerWidth <= 900;
}

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
  const textareaRef = useRef(null);
  const isEditing = Boolean(editing);

  // Вход/выход из edit-mode: подставить текст редактируемого сообщения либо очистить.
  useEffect(() => {
    setText(editing ? editing.text : '');
  }, [editing]);

  useLayoutEffect(() => {
    autosizeTextarea(textareaRef.current);
  }, [text, editing]);

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
    if (e.key === 'Enter') {
      if (isTouchComposerMode() || e.shiftKey) return;
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
        <textarea
          ref={textareaRef}
          className={styles.input}
          placeholder={isEditing ? 'Измените сообщение…' : 'Напишите сообщение…'}
          value={text}
          rows={1}
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
