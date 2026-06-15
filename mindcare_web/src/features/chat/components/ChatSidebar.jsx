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
 * Список диалогов разбит на секции (Stage 31v):
 *   «Архив»  — сверху, сворачиваемый блок (только если есть archivedContacts);
 *   «Сообщения» — активные диалоги (основной фокус);
 *   «Системные уведомления» — system-беседа (приходит внутри `contacts` с
 *     флагом `system`, выносится в отдельную секцию внизу).
 * Карточки во всех секциях — один и тот же ChatListItem с общим selected-стилем;
 * архивные лишь приглушены (muted) и вложены, но не «другой компонент».
 */
export default function ChatSidebar({ contacts, archivedContacts = [], activeId, onSelect }) {
  const [archiveOpen, setArchiveOpen] = useState(false);
  const hasArchive = archivedContacts.length > 0;
  const archiveUnread = archivedContacts.reduce((sum, c) => sum + (c.unread || 0), 0);

  const systemContacts = contacts.filter((c) => c.system);
  const activeContacts = contacts.filter((c) => !c.system);
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
          <section className={`${styles.section} ${styles.archiveSection}`}>
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
            {archiveOpen && (
              <div className={styles.archiveBody}>
                {archivedContacts.map((contact) => (
                  <ChatListItem
                    key={contact.id}
                    contact={{ ...contact, muted: true }}
                    isActive={contact.id === activeId}
                    onClick={() => onSelect(contact.id)}
                  />
                ))}
              </div>
            )}
          </section>
        )}

        {activeContacts.length > 0 && (
          <section className={`${styles.section} ${styles.messagesSection}`}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Сообщения</h2>
            </div>
            <div className={styles.sectionBody}>
              {activeContacts.map((contact) => (
                <ChatListItem
                  key={contact.id}
                  contact={contact}
                  isActive={contact.id === activeId}
                  onClick={() => onSelect(contact.id)}
                />
              ))}
            </div>
          </section>
        )}

        {systemContacts.length > 0 && (
          <section className={`${styles.section} ${styles.systemSection}`}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Системные уведомления</h2>
            </div>
            <div className={styles.sectionBody}>
              {systemContacts.map((contact) => (
                <ChatListItem
                  key={contact.id}
                  contact={contact}
                  isActive={contact.id === activeId}
                  onClick={() => onSelect(contact.id)}
                />
              ))}
            </div>
          </section>
        )}
      </div>
    </aside>
  );
}
