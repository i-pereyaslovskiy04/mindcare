import LinkifiedText from '../lib/LinkifiedText';
import styles from './MessageBubble.module.css';

/**
 * Чисто визуальное облачко сообщения (Stage 31z): текст + meta (время,
 * edited-метка, read receipts) внутри одного bubble, в стиле Telegram.
 * Никакой бизнес-логики — variant/props приходят готовыми из MessageItem.
 *
 * variant:
 *   outgoing — своё сообщение (тёмный bubble справа, time + receipts);
 *   incoming — сообщение собеседника (светлый bubble слева, только time);
 *   system   — системное уведомление MindCare (тот же фундамент, что incoming,
 *              чуть нейтральнее фон, без receipts).
 */
export default function MessageBubble({ variant = 'incoming', text, time, editedAt = null, readAt = null }) {
  const isOutgoing = variant === 'outgoing';
  const isSystem = variant === 'system';

  return (
    <div
      className={`${styles.bubble} ${isOutgoing ? styles.bubbleOutgoing : ''} ${isSystem ? styles.bubbleSystem : ''}`}
    >
      <div className={styles.text}>
        <LinkifiedText text={text} />
      </div>
      <div className={styles.meta}>
        {editedAt && <span className={styles.editedMark}>изменено </span>}
        <span className={styles.time}>{time}</span>
        {isOutgoing && (
          <span
            className={styles.receipt}
            title={readAt ? 'Прочитано' : 'Отправлено'}
            aria-label={readAt ? 'Прочитано' : 'Отправлено'}
          >
            {readAt ? '✓✓' : '✓'}
          </span>
        )}
      </div>
    </div>
  );
}
