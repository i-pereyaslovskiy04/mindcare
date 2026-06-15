import LinkifiedText from '../lib/LinkifiedText';
import styles from './ChatWindow.module.css';

export default function MessageItem({
  message,
  contactInitials,
  showAuthorHeader = false,
  authorName = '',
  authorRole = null,
}) {
  // Системное уведомление: нейтральный bubble, без аватара и без receipts.
  if (message.system) {
    return (
      <div className={styles.msgSystem}>
        <div className={styles.systemBubble}>
          <LinkifiedText text={message.text} />
          <div className={styles.systemTime}>{message.time}</div>
        </div>
      </div>
    );
  }

  const isMe = message.mine;

  return (
    <div className={`${styles.msg} ${isMe ? styles.msgMe : ''}`}>
      {!isMe && <div className={styles.msgAvatar}>{contactInitials}</div>}

      <div className={styles.msgContent}>
        {showAuthorHeader && (
          <div className={`${styles.authorHeader} ${isMe ? styles.authorHeaderMe : ''}`}>
            <span className={styles.authorName}>{authorName}</span>
            {authorRole && <span className={styles.authorRole}> · {authorRole}</span>}
          </div>
        )}
        <div className={`${styles.bubble} ${isMe ? styles.bubbleMe : ''}`}>
          <LinkifiedText text={message.text} />
        </div>
        <div className={`${styles.msgTime} ${isMe ? styles.msgTimeRight : ''}`}>
          {message.time}
          {isMe && (
            <span
              className={styles.receipt}
              title={message.readAt ? 'Прочитано' : 'Отправлено'}
              aria-label={message.readAt ? 'Прочитано' : 'Отправлено'}
            >
              {message.readAt ? '✓✓' : '✓'}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
