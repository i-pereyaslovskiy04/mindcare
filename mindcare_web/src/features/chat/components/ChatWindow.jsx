import { useCallback, useEffect, useState } from 'react';
import ChatHeader from './ChatHeader';
import MessageList from './MessageList';
import MessageInput from './MessageInput';
import DeleteMessageDialog from './DeleteMessageDialog';
import styles from './ChatWindow.module.css';

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

  // composer скрыт у системной беседы (readOnly) и у закрытого engagement.
  const showComposer = !readOnly && !closed;
  // действия (правка/удаление) возможны, пока есть composer (активный
  // engagement) и переданы соответствующие обработчики.
  const canManageChat = showComposer && (Boolean(onEdit) || Boolean(onDelete));

  // Если беседу закрыли/переключили — сбросить edit/delete-mode.
  useEffect(() => {
    if (!canManageChat) {
      setEditing(null);
      setPendingDelete(null);
    }
  }, [canManageChat, contact?.id]);

  const handleStartEdit = useCallback((message) => {
    setEditing({ uuid: message.uuid, text: message.text });
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

  if (!contact) return null;

  return (
    <div className={styles.window}>
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
    </div>
  );
}
