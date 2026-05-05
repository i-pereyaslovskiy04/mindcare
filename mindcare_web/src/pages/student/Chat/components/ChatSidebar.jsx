import ChatListItem from './ChatListItem';
import styles from './ChatSidebar.module.css';

export default function ChatSidebar({ contacts, activeId, onSelect }) {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.header}>
        <div className={styles.headerTitle}>Сообщения</div>
        <div className={styles.headerCount}>{contacts.length} диалога</div>
      </div>
      <div className={styles.list}>
        {contacts.map((contact) => (
          <ChatListItem
            key={contact.id}
            contact={contact}
            isActive={contact.id === activeId}
            onClick={() => onSelect(contact.id)}
          />
        ))}
      </div>
    </aside>
  );
}
