import Icon from '../../../components/Icon/Icon';
import styles from './ChatSidebar.module.css';

export default function ChatListItem({ contact, isActive, onClick }) {
  return (
    <button
      type="button"
      className={`${styles.item} ${isActive ? styles.itemActive : ''} ${contact.system ? styles.itemSystem : ''}`}
      onClick={onClick}
    >
      <div className={`${styles.avatar} ${contact.system ? styles.avatarSystem : ''}`}>
        {contact.system ? <Icon name="bell" size={18} /> : contact.initials}
      </div>

      <div className={styles.info}>
        <div className={styles.name}>{contact.name}</div>
        <div className={styles.lastMsg}>{contact.lastMsg}</div>
      </div>

      <div className={styles.meta}>
        <div className={styles.time}>{contact.time}</div>
        {contact.unread > 0 && (
          <span className={styles.unread}>{contact.unread}</span>
        )}
      </div>
    </button>
  );
}
