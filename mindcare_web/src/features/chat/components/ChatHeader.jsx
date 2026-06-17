import Icon from '../../../components/Icon/Icon';
import { hasPresence } from '../lib/conversationView';
import styles from './ChatWindow.module.css';

export default function ChatHeader({ contact, onBack = null }) {
  const showPresence = hasPresence(contact);

  return (
    <div className={styles.header}>
      {onBack && (
        <button
          type="button"
          className={styles.backBtn}
          onClick={onBack}
          aria-label="Назад к списку диалогов"
        >
          <Icon name="chevron-left" size={20} />
        </button>
      )}
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
