import { useCallback, useEffect, useRef, useState } from 'react';
import ChatHeader from './ChatHeader';
import MessageList from './MessageList';
import MessageInput from './MessageInput';
import DeleteMessageDialog from './DeleteMessageDialog';
import DragDropOverlay from './DragDropOverlay';
import { mergeSelectedFiles } from '../lib/attachmentSelection';
import styles from './ChatWindow.module.css';

function hasDragFiles(e) {
  if (!e.dataTransfer) return false;
  const { types } = e.dataTransfer;
  if (!types) return false;
  if (typeof types.includes === 'function') return types.includes('Files');
  if (typeof types.contains === 'function') return types.contains('Files');
  return false;
}

export default function ChatWindow({
  contact,
  messages,
  onSend,
  onEdit = null,
  onDelete = null,
  closed = false,
  sending = false,
  sendError = null,
  readOnly = false,
  readOnlyNotice = null,
  emptyText,
  onBack = null,
  onDownloadAttachment = null,
}) {
  // editing = { uuid, text } редактируемого сообщения либо null.
  const [editing, setEditing] = useState(null);
  // pendingDelete = сообщение, ожидающее подтверждения удаления, либо null.
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  // Выбранные, ещё не отправленные файлы (поднято из MessageInput — Stage 32f).
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [attachError, setAttachError] = useState(null);

  // Drag-and-drop state (Stage 32f).
  const [isDragOver, setIsDragOver] = useState(false);
  const dragCounterRef = useRef(0);

  // composer скрыт у системной беседы (readOnly) и у закрытого engagement.
  const showComposer = !readOnly && !closed;
  // действия (правка/удаление) возможны, пока есть composer (активный
  // engagement) и переданы соответствующие обработчики.
  const canManageChat = showComposer && (Boolean(onEdit) || Boolean(onDelete));

  // Сбросить состояние файлов и drag при смене беседы.
  useEffect(() => {
    setSelectedFiles([]);
    setAttachError(null);
    setIsDragOver(false);
    dragCounterRef.current = 0;
  }, [contact?.id]);

  // Если беседу закрыли/переключили — сбросить edit/delete-mode.
  useEffect(() => {
    if (!canManageChat) {
      setEditing(null);
      setPendingDelete(null);
    }
  }, [canManageChat, contact?.id]);

  const handleStartEdit = useCallback((message) => {
    setEditing({ uuid: message.uuid, text: message.text });
    // Очистить выбранные файлы при входе в edit-mode.
    setSelectedFiles([]);
    setAttachError(null);
  }, []);

  const handleCancelEdit = useCallback(() => setEditing(null), []);

  const handleSubmitEdit = useCallback(
    async (text) => {
      if (!editing) return false;
      const ok = await onEdit(editing.uuid, text);
      if (ok !== false) setEditing(null);
      return ok;
    },
    [editing, onEdit],
  );

  const handleRequestDelete = useCallback((message) => {
    setPendingDelete(message);
  }, []);

  const handleCancelDelete = useCallback(() => setPendingDelete(null), []);

  const handleConfirmDelete = useCallback(async () => {
    if (!pendingDelete || !onDelete) return;
    setDeleting(true);
    try {
      await onDelete(pendingDelete.uuid);
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  }, [pendingDelete, onDelete]);

  // --- управление выбранными файлами ---

  const handleFilesSelected = useCallback((rawFiles) => {
    setAttachError(null);
    const { files, error } = mergeSelectedFiles(selectedFiles, rawFiles);
    setSelectedFiles(files);
    if (error) setAttachError(error);
  }, [selectedFiles]);

  const handleRemoveFile = useCallback((index) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
    setAttachError(null);
  }, []);

  const handleClearFiles = useCallback(() => {
    setSelectedFiles([]);
    setAttachError(null);
  }, []);

  // --- drag-and-drop handlers ---

  const handleDragEnter = useCallback((e) => {
    if (!showComposer || !hasDragFiles(e)) return;
    dragCounterRef.current += 1;
    setIsDragOver(true);
  }, [showComposer]);

  const handleDragOver = useCallback((e) => {
    if (!showComposer || !hasDragFiles(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  }, [showComposer]);

  const handleDragLeave = useCallback(() => {
    if (dragCounterRef.current <= 0) return;
    dragCounterRef.current -= 1;
    if (dragCounterRef.current === 0) {
      setIsDragOver(false);
    }
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    dragCounterRef.current = 0;
    setIsDragOver(false);
    if (!showComposer) return;

    const droppedFiles = Array.from(e.dataTransfer?.files ?? []);
    if (droppedFiles.length === 0) return;

    const nonEmpty = droppedFiles.filter((f) => f.size > 0);
    if (nonEmpty.length === 0) {
      setAttachError('Пустой файл нельзя прикрепить.');
      return;
    }

    setAttachError(null);
    const { files, error } = mergeSelectedFiles(selectedFiles, nonEmpty);
    setSelectedFiles(files);
    if (error) setAttachError(error);
  }, [showComposer, selectedFiles]);

  if (!contact) return null;

  return (
    <div
      className={styles.window}
      data-testid="chat-window"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <ChatHeader contact={contact} onBack={onBack} />
      <MessageList
        messages={messages}
        contact={contact}
        emptyText={emptyText}
        manageable={canManageChat}
        onStartEdit={handleStartEdit}
        onRequestDelete={onDelete ? handleRequestDelete : null}
        onDownloadAttachment={onDownloadAttachment}
      />
      {sendError && (
        <div className={styles.sendError} role="alert">
          {sendError}
        </div>
      )}
      {showComposer ? (
        <MessageInput
          onSend={onSend}
          sending={sending}
          editing={editing}
          onSubmitEdit={handleSubmitEdit}
          onCancelEdit={handleCancelEdit}
          selectedFiles={selectedFiles}
          onFilesSelected={handleFilesSelected}
          onRemoveFile={handleRemoveFile}
          onClearFiles={handleClearFiles}
          attachError={attachError}
        />
      ) : (
        <div className={styles.closedNotice}>
          {readOnly
            ? readOnlyNotice
            : 'Диалог закрыт. История переписки доступна только для чтения.'}
        </div>
      )}

      <DeleteMessageDialog
        open={Boolean(pendingDelete)}
        deleting={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={handleCancelDelete}
      />

      <DragDropOverlay visible={isDragOver} />
    </div>
  );
}
