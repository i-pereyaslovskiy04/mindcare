import Icon from '../../../components/Icon/Icon';
import styles from './ChatWindow.module.css';

export default function ChatHeader({ contact }) {
  return (
    <div className={styles.header}>
      <div className={`${styles.headerAvatar} ${contact.system ? styles.headerAvatarSystem : ''}`}>
        {contact.system ? <Icon name="bell" size={18} /> : contact.initials}
      </div>

      <div className={styles.headerInfo}>
        <div className={styles.headerName}>{contact.name}</div>
        <div className={styles.headerStatus}>{contact.role}</div>
      </div>
    </div>
  );
}
