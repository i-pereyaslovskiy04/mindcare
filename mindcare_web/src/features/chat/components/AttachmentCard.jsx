import { useState } from 'react';
import Icon from '../../../components/Icon/Icon';
import styles from './AttachmentCard.module.css';

/** Форматирует байты в читаемый размер файла. */
export function formatFileSize(bytes) {
  if (bytes == null || bytes < 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Инициирует браузерное скачивание Blob-файла.
 * Создаёт временный <a>, кликает и немедленно отзывает object URL.
 */
export function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Компактная карточка вложения внутри сообщения (Stage 32d).
 *
 * Props:
 *   attachment      — нормализованный объект { uuid, originalFilename, mimeType,
 *                     fileSize, isImage, createdAt }
 *   onDownload      — async (attachment) => { blob, filename }; null/undefined → disabled
 *   disabled        — дополнительный disable (например, нет onDownload)
 */
export default function AttachmentCard({ attachment, onDownload, disabled = false }) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState(null);

  const displayName = attachment.originalFilename || 'Файл';
  const displaySize = formatFileSize(attachment.fileSize);
  const isDisabled = disabled || !onDownload || downloading;

  const handleDownload = async () => {
    if (isDisabled) return;
    setDownloading(true);
    setError(null);
    try {
      const { blob, filename } = await onDownload(attachment);
      const name = filename || displayName;
      triggerBlobDownload(blob, name);
    } catch {
      setError('Не удалось скачать файл.');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className={styles.card}>
      <span className={styles.fileIcon} aria-hidden="true">
        <Icon name={attachment.isImage ? 'image' : 'file'} size={16} />
      </span>
      <div className={styles.info}>
        <span className={styles.name} title={displayName}>
          {displayName}
        </span>
        {displaySize && <span className={styles.size}>{displaySize}</span>}
        {error && <span className={styles.error}>{error}</span>}
      </div>
      <button
        type="button"
        className={styles.downloadBtn}
        onClick={handleDownload}
        disabled={isDisabled}
        aria-label={downloading ? 'Загрузка…' : `Скачать ${displayName}`}
      >
        {downloading ? (
          <span className={styles.loadingDots} aria-hidden="true">…</span>
        ) : (
          <Icon name="download" size={14} aria-hidden="true" />
        )}
      </button>
    </div>
  );
}
