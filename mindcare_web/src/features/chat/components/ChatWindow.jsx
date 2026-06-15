import { useCallback, useEffect, useState } from 'react';
import ChatHeader from './ChatHeader';
import MessageList from './MessageList';
import MessageInput from './MessageInput';
import styles from './ChatWindow.module.css';

export default function ChatWindow({
  contact,
  messages,
  onSend,
  onEdit = null,
  closed = false,
  sending = false,
  sendError = null,
  readOnly = false,
  readOnlyNotice = null,
  emptyText,
  onBack = null,
}) {
  // editing = { uuid, text } редактируемого сообщения либо null.
  const [editing, setEditing] = useState(null);

  // composer скрыт у системной беседы (readOnly) и у закрытого engagement.
  const showComposer = !readOnly && !closed;
  // правка возможна только пока есть composer (активный engagement) и есть onEdit.
  const canEditChat = showComposer && Boolean(onEdit);

  // Если беседу закрыли/переключили — сбросить edit-mode.
  useEffect(() => {
    if (!canEditChat) setEditing(null);
  }, [canEditChat, contact?.id]);

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

  if (!contact) return null;

  return (
    <div className={styles.window}>
      <ChatHeader contact={contact} onBack={onBack} />
      <MessageList
        messages={messages}
        contact={contact}
        emptyText={emptyText}
        editable={canEditChat}
        onStartEdit={handleStartEdit}
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
    </div>
  );
}
