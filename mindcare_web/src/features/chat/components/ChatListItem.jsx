import Icon from '../../../components/Icon/Icon';
import styles from './ChatSidebar.module.css';

export default function ChatListItem({ contact, isActive, onClick }) {
  const hasUnread = contact.unread > 0;
  // presence показываем только у обычных диалогов (у system-беседы его нет).
  const showPresence = !contact.system && typeof contact.online === 'boolean';

  return (
    <button
      type="button"
      className={[
        styles.item,
        isActive ? styles.itemActive : '',
        contact.system ? styles.itemSystem : '',
        hasUnread ? styles.itemUnread : '',
      ].filter(Boolean).join(' ')}
      onClick={onClick}
    >
      <div className={`${styles.avatar} ${contact.system ? styles.avatarSystem : ''}`}>
        {contact.system ? <Icon name="bell" size={18} /> : contact.initials}
        {hasUnread && <span className={styles.unreadDot} aria-hidden="true" />}
        {showPresence && (
          <span
            className={`${styles.presenceDot} ${
              contact.online ? styles.presenceOnline : styles.presenceOffline
            }`}
            aria-hidden="true"
          />
        )}
      </div>

      <div className={styles.info}>
        <div className={`${styles.name} ${hasUnread ? styles.nameUnread : ''}`}>
          {contact.name}
        </div>
        <div className={styles.lastMsg}>{contact.lastMsg}</div>
      </div>

      <div className={styles.meta}>
        <div className={styles.time}>{contact.time}</div>
        {hasUnread && <span className={styles.unread}>{contact.unread}</span>}
      </div>
    </button>
  );
}
