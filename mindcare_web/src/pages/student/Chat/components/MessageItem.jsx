import styles from './ChatWindow.module.css';

export default function MessageItem({ message, contactInitials }) {
  const isMe = message.sender === 'me';

  return (
    <div className={`${styles.msg} ${isMe ? styles.msgMe : ''}`}>
      {!isMe && <div className={styles.msgAvatar}>{contactInitials}</div>}

      <div className={styles.msgContent}>
        <div className={`${styles.bubble} ${isMe ? styles.bubbleMe : ''}`}>
          {message.text}
        </div>
        <div className={`${styles.msgTime} ${isMe ? styles.msgTimeRight : ''}`}>
          {message.time}
        </div>
      </div>
    </div>
  );
}
