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

  // Удалённое сообщение полностью скрыто из ленты (Stage 31y-hotfix): без bubble
  // и без плейсхолдера «Сообщение удалено». Defense-in-depth — MessageList и так
  // отфильтровывает deleted до рендера, но на случай прямой передачи возвращаем null.
  if (message.deleted) return null;

  const isMe = message.mine;

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
