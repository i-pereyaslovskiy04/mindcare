import Icon from '../../../components/Icon/Icon';
import styles from './ChatWindow.module.css';

export default function ChatHeader({ contact }) {
  // presence показываем только у обычных диалогов (у system-беседы его нет).
  const showPresence = !contact.system && typeof contact.online === 'boolean';

  return (
    <div className={styles.header}>
      <div className={`${styles.headerAvatar} ${contact.system ? styles.headerAvatarSystem : ''}`}>
        {contact.system ? <Icon name="bell" size={18} /> : contact.initials}
      </div>

      <div className={styles.headerInfo}>
        <div className={styles.headerName}>{contact.name}</div>
        <div className={styles.headerStatus}>
          <span>{contact.role}</span>
          {showPresence && (
            <span className={styles.presence}>
              <span
                className={`${styles.presenceDot} ${
                  contact.online ? styles.presenceOnline : styles.presenceOffline
                }`}
                aria-hidden="true"
              />
              {contact.online ? 'Онлайн' : 'Офлайн'}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
