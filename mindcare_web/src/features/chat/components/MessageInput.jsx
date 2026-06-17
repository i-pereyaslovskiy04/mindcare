import { useState, useEffect, useCallback, useLayoutEffect, useRef } from 'react';
import Icon from '../../../components/Icon/Icon';
import SelectedAttachmentList from './SelectedAttachmentList';
import EditableAttachmentList from './EditableAttachmentList';
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
 * Composer (Stage 32e/32f/32g):
 *   - Обычная отправка: onSend(text, files) — text и/или файлы.
 *   - Редактирование: editing = { uuid, text, attachments, removedUuids } →
 *     onSubmitEdit(text); скрепка скрыта; показывается EditableAttachmentList.
 *   - selectedFiles / attachError / управление файлами хранятся в ChatWindow (Stage 32f).
 *
 * onSend возвращает false при ошибке — текст и файлы НЕ очищаются.
 */
export default function MessageInput({
  onSend,
  sending = false,
  editing = null,
  onSubmitEdit = null,
  onCancelEdit = null,
  onRemoveEditAttachment = null,
  // Selected files owned by ChatWindow (Stage 32f)
  selectedFiles = [],
  onFilesSelected = null,
  onRemoveFile = null,
  onClearFiles = null,
  attachError = null,
}) {
  const [text, setText] = useState('');
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const isEditing = Boolean(editing);

  // Stage 32g: вложения и список убираемых UUID из текущего editing state.
  const editingAtts = editing?.attachments || [];
  const editingRemovedUuids = editing?.removedUuids || [];
  const remainingEditAtts = editingAtts.filter((a) => !editingRemovedUuids.includes(a.uuid));

  // Подставить текст при входе в edit-mode, очистить при выходе.
  useEffect(() => {
    setText(editing ? editing.text : '');
  }, [editing]);

  useLayoutEffect(() => {
    autosizeTextarea(textareaRef.current);
  }, [text, editing, selectedFiles, editingRemovedUuids]);

  const handleFileChange = (e) => {
    onFilesSelected?.(e.target.files);
    // Сбросить value, чтобы тот же файл можно было выбрать повторно.
    e.target.value = '';
  };

  const handleSubmit = useCallback(async () => {
    const trimmed = text.trim();
    const hasFiles = selectedFiles.length > 0;
    if (sending) return;

    if (isEditing) {
      // Разрешён пустой текст, если есть оставшиеся вложения (Stage 32g).
      if (!trimmed && remainingEditAtts.length === 0) return;
      const ok = await onSubmitEdit(trimmed);
      // При ошибке — текст сохраняем, чтобы правка не потерялась.
      if (ok === false) return;
    } else {
      if (!trimmed && !hasFiles) return;
      const ok = await onSend(trimmed, selectedFiles);
      if (ok !== false) {
        setText('');
        onClearFiles?.();
      }
      // При ok === false — текст и файлы НЕ трогаем: пользователь видит черновик.
    }
  }, [text, selectedFiles, sending, isEditing, remainingEditAtts, onSend, onSubmitEdit, onClearFiles]);

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

  const canSend = isEditing
    ? ((text.trim().length > 0 || remainingEditAtts.length > 0) && !sending)
    : ((text.trim().length > 0 || selectedFiles.length > 0) && !sending);

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

      {/* Выбранные файлы — только вне edit-mode */}
      {!isEditing && (
        <SelectedAttachmentList
          files={selectedFiles}
          onRemove={onRemoveFile}
          uploading={sending}
        />
      )}

      {/* Вложения редактируемого сообщения — только в edit-mode (Stage 32g) */}
      {isEditing && editingAtts.length > 0 && (
        <EditableAttachmentList
          attachments={editingAtts}
          removedUuids={editingRemovedUuids}
          onRemove={onRemoveEditAttachment}
          disabled={sending}
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
