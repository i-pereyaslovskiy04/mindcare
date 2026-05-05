import ChatHeader from './ChatHeader';
import MessageList from './MessageList';
import MessageInput from './MessageInput';
import styles from './ChatWindow.module.css';

export default function ChatWindow({ contact, messages, onSend }) {
  if (!contact) return null;

  return (
    <div className={styles.window}>
      <ChatHeader contact={contact} />
      <MessageList messages={messages} contact={contact} />
      <MessageInput onSend={onSend} />
    </div>
  );
}
