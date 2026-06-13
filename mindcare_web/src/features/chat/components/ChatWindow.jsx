import ChatHeader from './ChatHeader';
import MessageList from './MessageList';
import MessageInput from './MessageInput';
import styles from './ChatWindow.module.css';

export default function ChatWindow({
  contact,
  messages,
  onSend,
  closed = false,
  sending = false,
  sendError = null,
  readOnly = false,
  readOnlyNotice = null,
  emptyText,
}) {
  if (!contact) return null;

  // composer скрыт у системной беседы (readOnly) и у закрытого engagement.
  const showComposer = !readOnly && !closed;

  return (
    <div className={styles.window}>
      <ChatHeader contact={contact} />
      <MessageList messages={messages} contact={contact} emptyText={emptyText} />
      {sendError && (
        <div className={styles.sendError} role="alert">
          {sendError}
        </div>
      )}
      {showComposer ? (
        <MessageInput onSend={onSend} sending={sending} />
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
