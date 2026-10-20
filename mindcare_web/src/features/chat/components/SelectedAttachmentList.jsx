import Icon from '../../../components/Icon/Icon';
import { formatFileSize } from './AttachmentCard';
import styles from './SelectedAttachmentList.module.css';

/**
 * Список выбранных, но ещё не отправленных файлов (над composer).
 * files — массив Browser File объектов.
 */
export default function SelectedAttachmentList({ files, onRemove, uploading = false }) {
  if (!files || files.length === 0) return null;

  return (
    <div className={styles.list}>
      {files.map((file, index) => {
        const isImage = file.type.startsWith('image/');
        return (
          <div
            key={`${file.name}-${file.size}-${index}`}
            className={styles.item}
          >
            <span className={styles.fileIcon} aria-hidden="true">
              <Icon name={isImage ? 'image' : 'file'} size={14} />
            </span>
            <span className={styles.name} title={file.name}>{file.name}</span>
            <span className={styles.size}>{formatFileSize(file.size)}</span>
            <button
              type="button"
              className={styles.removeBtn}
              onClick={() => onRemove(index)}
              disabled={uploading}
              aria-label={`Убрать ${file.name}`}
            >
              <Icon name="x" size={12} aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
