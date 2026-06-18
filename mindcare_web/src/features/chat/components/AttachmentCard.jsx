import { useState } from 'react';
import { saveBlobToDisk } from '../../../api/client';
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
 * Компактная карточка вложения внутри сообщения (Stage 32d).
 *
 * Props:
 *   attachment      — нормализованный объект { uuid, originalFilename, mimeType,
 *                     fileSize, isImage, createdAt }
 *   onDownload      — async (attachment) => { blob, filename }; null/undefined → disabled
 *   disabled        — дополнительный disable (например, нет onDownload)
 */
export default function AttachmentCard({ attachment, onDownload, disabled = false, outgoing = false }) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState(null);

  const displayName = attachment.originalFilename || 'Файл';
  const displaySize = formatFileSize(attachment.fileSize);
  const isDisabled = disabled || !onDownload || downloading;

  const handleDownload = async (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (isDisabled) return;

    setDownloading(true);
    setError(null);

    // saveBlobToDisk вызывается без предшествующих await — user activation
    // window сохраняется для showSaveFilePicker (Chromium primary path).
    try {
      await saveBlobToDisk(
        async () => {
          const { blob } = await onDownload(attachment);
          return blob;
        },
        displayName,
      );
    } catch (err) {
      // AbortError = пользователь отменил save-диалог; не ошибка.
      if (err?.name !== 'AbortError') {
        setError('Не удалось скачать файл.');
      }
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className={`${styles.card} ${outgoing ? styles.cardOutgoing : ''}`}>
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
