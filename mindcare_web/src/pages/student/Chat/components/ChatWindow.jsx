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
}) {
  if (!contact) return null;

  return (
    <div className={styles.window}>
      <ChatHeader contact={contact} />
      <MessageList messages={messages} contact={contact} />
      {sendError && (
        <div className={styles.sendError} role="alert">
          {sendError}
        </div>
      )}
      {closed ? (
        <div className={styles.closedNotice}>
          Диалог закрыт. История переписки доступна только для чтения.
        </div>
      ) : (
        <MessageInput onSend={onSend} sending={sending} />
      )}
    </div>
  );
}
