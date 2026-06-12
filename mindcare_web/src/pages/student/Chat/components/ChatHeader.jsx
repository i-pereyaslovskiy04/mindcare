import styles from './ChatWindow.module.css';

export default function ChatHeader({ contact }) {
  return (
    <div className={styles.header}>
      <div className={styles.headerAvatar}>{contact.initials}</div>

      <div className={styles.headerInfo}>
        <div className={styles.headerName}>{contact.name}</div>
        <div className={styles.headerStatus}>{contact.role}</div>
      </div>
    </div>
  );
}
