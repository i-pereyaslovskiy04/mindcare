import Icon from '../../../components/Icon/Icon';
import MessageActionsMenu from './MessageActionsMenu';
import MessageBubble from './MessageBubble';
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
  // Удалённое сообщение полностью скрыто из ленты (Stage 31y-hotfix): без bubble
  // и без плейсхолдера «Сообщение удалено». Defense-in-depth — MessageList и так
  // отфильтровывает deleted до рендера, но на случай прямой передачи возвращаем null.
  if (message.deleted) return null;

  const isSystem = Boolean(message.system);
  // system messages никогда не "мои", даже если backend когда-нибудь пришлёт
  // mine=true вместе с system=true — иначе system-сообщение получило бы
  // outgoing-layout (actions menu/read receipts/право-выровненный bubble).
  const isMe = !isSystem && message.mine;
  const variant = isSystem ? 'system' : isMe ? 'outgoing' : 'incoming';

  // Меню действий: только своё user-сообщение, чат управляем (manageable), есть uuid.
  const canManage = manageable && isMe && !isSystem && Boolean(message.uuid);

  return (
    <div className={`${styles.msg} ${isMe ? styles.msgMe : ''}`}>
      {!isMe && (
        <div className={`${styles.msgAvatar} ${isSystem ? styles.msgAvatarSystem : ''}`}>
          {isSystem ? <Icon name="bell" size={14} /> : contactInitials}
        </div>
      )}

      <div className={styles.msgContent}>
        {showAuthorHeader && (
          <div className={`${styles.authorHeader} ${isMe ? styles.authorHeaderMe : ''}`}>
            <span className={styles.authorName}>{authorName}</span>
            {authorRole && <span className={styles.authorRole}> · {authorRole}</span>}
          </div>
        )}
        {/* bubble + меню действий в одной строке: kebab центрируется по высоте
            bubble (а не по всей колонке с meta/time, теперь внутри bubble). */}
        <div className={styles.bubbleRow}>
          <MessageBubble
            variant={variant}
            text={message.text}
            time={message.time}
            editedAt={message.editedAt}
            readAt={message.readAt}
          />
          {canManage && (
            <MessageActionsMenu
              triggerClassName={styles.msgActions}
              onEdit={() => onStartEdit?.(message)}
              onDelete={() => onRequestDelete?.(message)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
