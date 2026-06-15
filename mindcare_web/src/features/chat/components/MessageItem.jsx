import Icon from '../../../components/Icon/Icon';
import LinkifiedText from '../lib/LinkifiedText';
import styles from './ChatWindow.module.css';

export default function MessageItem({
  message,
  contactInitials,
  showAuthorHeader = false,
  authorName = '',
  authorRole = null,
  editable = false,
  onStartEdit = null,
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
  // Карандаш: только своё user-сообщение, чат активен (editable), есть uuid.
  const canEdit = editable && isMe && !message.system && Boolean(message.uuid);

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
        {/* bubble + карандаш в одной строке: карандаш центрируется по высоте
            самого bubble, а не по всей колонке с meta/time (Stage 31x-hotfix). */}
        <div className={styles.bubbleRow}>
          <div className={`${styles.bubble} ${isMe ? styles.bubbleMe : ''}`}>
            <LinkifiedText text={message.text} />
          </div>
          {canEdit && (
            <button
              type="button"
              className={styles.editBtn}
              onClick={() => onStartEdit(message)}
              aria-label="Редактировать сообщение"
            >
              <Icon name="edit" size={14} />
            </button>
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
