import { useState } from 'react';
import ChatListItem from './ChatListItem';
import styles from './ChatSidebar.module.css';

function dialogWord(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'диалог';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'диалога';
  return 'диалогов';
}

/**
 * Список диалогов. Порядок: «Архив» (свёрнут по умолчанию) → активные →
 * системная беседа (она передаётся внутри `contacts` последней). archivedContacts
 * рендерятся только при раскрытии и не входят в основной список.
 */
export default function ChatSidebar({ contacts, archivedContacts = [], activeId, onSelect }) {
  const [archiveOpen, setArchiveOpen] = useState(false);
  const hasArchive = archivedContacts.length > 0;
  const archiveUnread = archivedContacts.reduce((sum, c) => sum + (c.unread || 0), 0);
  const total = contacts.length + archivedContacts.length;

  return (
    <aside className={styles.sidebar}>
      <div className={styles.header}>
        <div className={styles.headerTitle}>Сообщения</div>
        <div className={styles.headerCount}>
          {total} {dialogWord(total)}
        </div>
      </div>
      <div className={styles.list}>
        {hasArchive && (
          <>
            <button
              type="button"
              className={styles.archiveRow}
              aria-expanded={archiveOpen}
              onClick={() => setArchiveOpen((v) => !v)}
            >
              <span
                className={`${styles.archiveChevron} ${archiveOpen ? styles.archiveChevronOpen : ''}`}
                aria-hidden="true"
              >
                ▸
              </span>
              <span className={styles.archiveTitle}>Архив</span>
              <span className={styles.archiveCount}>{archivedContacts.length}</span>
              {archiveUnread > 0 && (
                <span className={styles.archiveUnread}>{archiveUnread}</span>
              )}
            </button>
            {archiveOpen &&
              archivedContacts.map((contact) => (
                <ChatListItem
                  key={contact.id}
                  contact={contact}
                  isActive={contact.id === activeId}
                  onClick={() => onSelect(contact.id)}
                />
              ))}
          </>
        )}
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
