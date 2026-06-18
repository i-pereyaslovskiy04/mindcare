import { useEffect, useState } from 'react';
import { saveBlobToDisk } from '../../../api/client';
import Icon from '../../../components/Icon/Icon';
import ImageLightbox from './ImageLightbox';
import styles from './AttachmentCard.module.css';

/** Форматирует байты в читаемый размер файла. */
export function formatFileSize(bytes) {
  if (bytes == null || bytes < 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// SVG намеренно исключён: может содержать скрипты.
const PREVIEW_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

/**
 * Компактная карточка вложения внутри сообщения (Stage 32d/32i).
 *
 * Props:
 *   attachment      — нормализованный объект { uuid, originalFilename, mimeType,
 *                     fileSize, isImage, createdAt }
 *   onDownload      — async (attachment) => { blob, filename }; null/undefined → disabled
 *   disabled        — дополнительный disable (например, нет onDownload)
 *   outgoing        — true для исходящего bubble
 */
export default function AttachmentCard({ attachment, onDownload, disabled = false, outgoing = false }) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState(null);

  // Состояние лайтбокса.
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewObjectUrl, setPreviewObjectUrl] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(null);

  const displayName = attachment.originalFilename || 'Файл';
  const displaySize = formatFileSize(attachment.fileSize);
  const isDisabled = disabled || !onDownload || downloading;

  // Изображение можно просмотреть только при явно разрешённом MIME (без SVG).
  const isPreviewable = Boolean(
    attachment.isImage &&
    attachment.mimeType &&
    PREVIEW_MIME_TYPES.includes(attachment.mimeType) &&
    onDownload,
  );

  // Revoke object URL при смене или unmount — защита от memory leak.
  useEffect(() => {
    return () => {
      if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
    };
  }, [previewObjectUrl]);

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

  const handleOpenPreview = async (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!isPreviewable) return;

    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewError(null);

    try {
      const { blob } = await onDownload(attachment);
      const url = URL.createObjectURL(blob);
      setPreviewObjectUrl(url);
    } catch {
      setPreviewError('Не удалось загрузить изображение.');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleClosePreview = () => {
    setPreviewOpen(false);
    // previewObjectUrl будет revoke-нут через useEffect при обнулении.
    setPreviewObjectUrl(null);
    setPreviewError(null);
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
      {isPreviewable && (
        <button
          type="button"
          className={styles.previewBtn}
          onClick={handleOpenPreview}
          aria-label={`Открыть ${displayName}`}
          data-testid="preview-btn"
        >
          <Icon name="eye" size={14} aria-hidden="true" />
        </button>
      )}
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

      {previewOpen && (
        <ImageLightbox
          attachment={attachment}
          objectUrl={previewObjectUrl}
          loading={previewLoading}
          error={previewError}
          onClose={handleClosePreview}
        />
      )}
    </div>
  );
}
