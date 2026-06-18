import { useEffect } from 'react';
import Icon from '../../../components/Icon/Icon';
import styles from './ImageLightbox.module.css';

/**
 * Лайтбокс для просмотра изображений из вложений чата (Stage 32i).
 * Открывается поверх чата с затемнённым overlay.
 * Изображение передаётся как objectUrl (blob:), созданный вызывающей стороной.
 *
 * Props:
 *   attachment  — { originalFilename, ... }
 *   objectUrl   — blob: URL для <img>, создан вызывающей стороной
 *   loading     — показывать spinner/loading text
 *   error       — строка ошибки или null
 *   onClose     — вызвать при закрытии
 */
export default function ImageLightbox({ attachment, objectUrl, loading, error, onClose }) {
  const displayName = attachment?.originalFilename || 'Изображение';

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
      aria-label={`Просмотр изображения: ${displayName}`}
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
        className={styles.content}
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
        {objectUrl && !loading && !error && (
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
