import Icon from '../../../components/Icon/Icon';
import { formatFileSize } from './AttachmentCard';
import styles from './EditableAttachmentList.module.css';

/**
 * Список вложений сообщения в режиме редактирования (Stage 32g).
 * Показывает активные (не помеченные к удалению) вложения с кнопкой убрать.
 * Помеченные к удалению скрываются немедленно (оптимистичный UI).
 *
 * Props:
 *   attachments    — нормализованные attachment-объекты текущего сообщения
 *   removedUuids   — массив UUID, уже помеченных к удалению
 *   onRemove       — (uuid: string) => void
 *   disabled       — bool, блокирует кнопки (например во время sending)
 */
export default function EditableAttachmentList({
  attachments = [],
  removedUuids = [],
  onRemove = null,
  disabled = false,
}) {
  const visible = attachments.filter((a) => !removedUuids.includes(a.uuid));
  if (visible.length === 0) return null;

  return (
    <div className={styles.list}>
      {visible.map((att) => {
        const name = att.originalFilename || 'Файл';
        const size = formatFileSize(att.fileSize);
        return (
          <div key={att.uuid} className={styles.item}>
            <span className={styles.fileIcon} aria-hidden="true">
              <Icon name={att.isImage ? 'image' : 'file'} size={14} />
            </span>
            <span className={styles.name} title={name}>{name}</span>
            {size && <span className={styles.size}>{size}</span>}
            <button
              type="button"
              className={styles.removeBtn}
              onClick={() => onRemove?.(att.uuid)}
              disabled={disabled || !onRemove}
              aria-label={`Убрать ${name}`}
            >
              <Icon name="x" size={12} aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
