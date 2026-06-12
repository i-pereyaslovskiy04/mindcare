import ChatListItem from './ChatListItem';
import styles from './ChatSidebar.module.css';

function dialogWord(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'диалог';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'диалога';
  return 'диалогов';
}

export default function ChatSidebar({ contacts, activeId, onSelect }) {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.header}>
        <div className={styles.headerTitle}>Сообщения</div>
        <div className={styles.headerCount}>
          {contacts.length} {dialogWord(contacts.length)}
        </div>
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
