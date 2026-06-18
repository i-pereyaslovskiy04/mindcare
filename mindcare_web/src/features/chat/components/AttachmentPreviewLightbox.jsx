import { useEffect } from 'react';
import Icon from '../../../components/Icon/Icon';
import styles from './AttachmentPreviewLightbox.module.css';

/**
 * Лайтбокс для просмотра вложений чата: изображения и PDF (Stage 32i/32j).
 * Blob-URL создаётся вызывающей стороной (AttachmentCard) через authenticated
 * download handler — public static URLs не используются.
 *
 * variant определяется автоматически по attachment.mimeType:
 *   image/jpeg | image/png | image/webp  → <img>
 *   application/pdf                      → <iframe>
 *
 * Props:
 *   attachment  — { originalFilename, mimeType, ... }
 *   objectUrl   — blob: URL, создан вызывающей стороной
 *   loading     — показывать loading state
 *   error       — строка ошибки или null
 *   onClose     — вызвать при закрытии
 */
export default function AttachmentPreviewLightbox({ attachment, objectUrl, loading, error, onClose }) {
  const displayName = attachment?.originalFilename || 'Файл';
  const isPdf = attachment?.mimeType === 'application/pdf';

  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  return (
    <div
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-label={`Просмотр: ${displayName}`}
      onClick={onClose}
      data-testid="lightbox-overlay"
    >
      <button
        type="button"
        className={styles.closeBtn}
        onClick={(e) => { e.stopPropagation(); onClose(); }}
        aria-label="Закрыть просмотр"
        data-testid="lightbox-close"
      >
        <Icon name="x" size={20} aria-hidden="true" />
      </button>
      <div
        className={`${styles.content} ${isPdf ? styles.contentPdf : ''}`}
        onClick={(e) => e.stopPropagation()}
        data-testid="lightbox-content"
      >
        {loading && (
          <div className={styles.status} role="status" data-testid="lightbox-loading">
            Загрузка…
          </div>
        )}
        {error && !loading && (
          <div className={styles.status} role="alert" data-testid="lightbox-error">
            {error}
          </div>
        )}
        {objectUrl && !loading && !error && isPdf && (
          <iframe
            src={objectUrl}
            title={displayName}
            className={styles.pdfFrame}
            data-testid="lightbox-pdf"
          />
        )}
        {objectUrl && !loading && !error && !isPdf && (
          <img
            src={objectUrl}
            alt={displayName}
            className={styles.image}
            data-testid="lightbox-image"
          />
        )}
      </div>
    </div>
  );
}
