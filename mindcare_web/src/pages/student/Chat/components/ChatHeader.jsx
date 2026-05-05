import Icon from '../../components/Icon';
import styles from './ChatWindow.module.css';

export default function ChatHeader({ contact }) {
  return (
    <div className={styles.header}>
      <div className={styles.headerAvatar}>{contact.initials}</div>

      <div className={styles.headerInfo}>
        <div className={styles.headerName}>{contact.name}</div>
        <div className={styles.headerStatus}>
          {contact.online && <span className={styles.statusDot} />}
          {contact.online ? 'в сети · отвечает обычно за 30 мин' : contact.role}
        </div>
      </div>

      <button className={styles.videoBtn} aria-label="Видеозвонок">
        <Icon name="video" size={16} />
      </button>
    </div>
  );
}
