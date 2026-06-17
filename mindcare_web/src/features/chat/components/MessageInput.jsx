import { useState, useEffect, useCallback, useLayoutEffect, useRef } from 'react';
import Icon from '../../../components/Icon/Icon';
import SelectedAttachmentList from './SelectedAttachmentList';
import styles from './ChatWindow.module.css';

const MAX_LENGTH = 10000; // лимит backend-валидации ChatMessageCreate/Edit
const MAX_FILES = 5;      // мягкий client-side лимит (backend — источник истины)
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
 * Composer (Stage 32e):
 *   - обычная отправка: onSend(text, files) — text и/или файлы;
 *   - редактирование: editing = { uuid, text } → onSubmitEdit(text); скрепка скрыта.
 *
 * onSend возвращает false при ошибке — текст и файлы НЕ очищаются.
 */
export default function MessageInput({
  onSend,
  sending = false,
  editing = null,
  onSubmitEdit = null,
  onCancelEdit = null,
}) {
  const [text, setText] = useState('');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [attachError, setAttachError] = useState(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const isEditing = Boolean(editing);

  // Вход/выход из edit-mode: подставить текст редактируемого сообщения либо очистить.
  useEffect(() => {
    setText(editing ? editing.text : '');
    if (!editing) setSelectedFiles([]);
  }, [editing]);

  useLayoutEffect(() => {
    autosizeTextarea(textareaRef.current);
  }, [text, editing, selectedFiles]);

  const handleFiles = useCallback((rawFiles) => {
    setAttachError(null);
    const valid = [...rawFiles].filter((f) => f.size > 0);
    const next = [...selectedFiles, ...valid];
    if (next.length > MAX_FILES) {
      setAttachError(`Максимум ${MAX_FILES} файлов за раз.`);
      setSelectedFiles(next.slice(0, MAX_FILES));
      return;
    }
    setSelectedFiles(next);
  }, [selectedFiles]);

  const handleFileChange = (e) => {
    handleFiles(e.target.files);
    // Сбросить value, чтобы тот же файл можно было выбрать повторно.
    e.target.value = '';
  };

  const handleRemoveFile = useCallback((index) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
    setAttachError(null);
  }, []);

  const handleSubmit = useCallback(async () => {
    const trimmed = text.trim();
    const hasFiles = selectedFiles.length > 0;
    if (!trimmed && !hasFiles) return;
    if (sending) return;

    if (isEditing) {
      if (!trimmed) return; // edit требует текст
      const ok = await onSubmitEdit(trimmed);
      // При успехе родитель сбросит editing→null (useEffect очистит input).
      // При ошибке текст сохраняем, чтобы правка не потерялась.
      if (ok === false) return;
    } else {
      const ok = await onSend(trimmed, selectedFiles);
      if (ok !== false) {
        setText('');
        setSelectedFiles([]);
        setAttachError(null);
      }
      // При ok === false — текст и файлы НЕ трогаем: пользователь видит черновик.
    }
  }, [text, selectedFiles, sending, isEditing, onSend, onSubmitEdit]);

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

  const canSend = (text.trim().length > 0 || selectedFiles.length > 0) && !sending;

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

      {/* Выбранные, но ещё не отправленные файлы — только вне edit-mode */}
      {!isEditing && (
        <SelectedAttachmentList
          files={selectedFiles}
          onRemove={handleRemoveFile}
          uploading={sending}
        />
      )}

      {attachError && (
        <div className={styles.attachError} role="alert">{attachError}</div>
      )}

      <div className={styles.inputRow}>
        {!isEditing && (
          <>
            <button
              type="button"
              className={styles.attachBtn}
              onClick={() => fileInputRef.current?.click()}
              disabled={sending}
              aria-label="Прикрепить файл"
            >
              <Icon name="paperclip" size={16} aria-hidden="true" />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className={styles.fileInput}
              onChange={handleFileChange}
            />
          </>
        )}
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
          disabled={!canSend}
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
