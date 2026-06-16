import LinkifiedText from '../lib/LinkifiedText';
import MessageActionsMenu from './MessageActionsMenu';
import styles from './ChatWindow.module.css';

export default function MessageItem({
  message,
  contactInitials,
  showAuthorHeader = false,
  authorName = '',
  authorRole = null,
  manageable = false,
  onStartEdit = null,
  onRequestDelete = null,
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

  // Удалённое сообщение: нейтральный placeholder, без content/linkify, без меню,
  // без receipts и метки «изменено». История не становится «дырявой».
  if (message.deleted) {
    return (
      <div className={`${styles.msg} ${isMe ? styles.msgMe : ''}`}>
        {!isMe && <div className={styles.msgAvatar}>{contactInitials}</div>}
        <div className={styles.msgContent}>
          <div className={styles.bubbleRow}>
            <div className={`${styles.bubble} ${styles.bubbleDeleted}`}>
              Сообщение удалено
            </div>
          </div>
          <div className={`${styles.msgTime} ${isMe ? styles.msgTimeRight : ''}`}>
            {message.time}
          </div>
        </div>
      </div>
    );
  }

  // Меню действий: только своё user-сообщение, чат управляем (manageable), есть uuid.
  const canManage = manageable && isMe && !message.system && Boolean(message.uuid);

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
        {/* bubble + меню действий в одной строке: kebab центрируется по высоте
            bubble (а не по всей колонке с meta/time). */}
        <div className={styles.bubbleRow}>
          <div className={`${styles.bubble} ${isMe ? styles.bubbleMe : ''}`}>
            <LinkifiedText text={message.text} />
          </div>
          {canManage && (
            <MessageActionsMenu
              triggerClassName={styles.msgActions}
              onEdit={() => onStartEdit?.(message)}
              onDelete={() => onRequestDelete?.(message)}
            />
          )}
        </div>
        <div className={`${styles.msgTime} ${isMe ? styles.msgTimeRight : ''}`}>
          {message.time}
          {message.editedAt && <span className={styles.editedMark}> · изменено</span>}
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
