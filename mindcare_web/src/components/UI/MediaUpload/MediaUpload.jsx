import { useEffect, useRef, useState } from 'react';
import { uploadMedia } from '../../../api/media.api';
import styles from './MediaUpload.module.css';

// Лимит размера — из backend /api/public/config (mediaAvMaxSizeMb). Запрашивается
// один раз и переиспользуется между монтированиями (как в ImageUpload).
let _configPromise = null;
function fetchServerConfig() {
  if (!_configPromise) {
    _configPromise = fetch('/api/public/config')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
      .catch(() => null);
  }
  return _configPromise;
}

/**
 * Загрузка аудио/видео (для вопросов тестов). value — { uuid, url, kind } | null.
 * Превью — нативный плеер <audio>/<video controls>; длительность показывает сам
 * браузер (backend её не извлекает).
 */
export default function MediaUpload({ value, onChange, label = 'Аудио или видео' }) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [maxMb, setMaxMb] = useState(null);

  useEffect(() => {
    fetchServerConfig().then((cfg) => setMaxMb(cfg?.mediaAvMaxSizeMb ?? 50));
  }, []);

  const configLoading = maxMb === null;

  async function handleFile(file) {
    if (!file || configLoading) return;
    setError('');
    if (file.size > maxMb * 1024 * 1024) {
      setError(`Файл превышает ${maxMb} МБ`);
      return;
    }
    setUploading(true);
    try {
      const result = await uploadMedia(file);
      onChange({ uuid: result.uuid, url: result.url, kind: result.file_type });
    } catch (err) {
      setError(err.message || 'Ошибка загрузки');
    } finally {
      setUploading(false);
    }
  }

  function handleRemove() {
    onChange(null);
    if (inputRef.current) inputRef.current.value = '';
  }

  const isDisabled = configLoading || uploading;

  return (
    <div className={styles.wrap}>
      <span className={styles.label}>{label}</span>

      {value?.url ? (
        <div className={styles.preview}>
          {value.kind === 'video' ? (
            <video className={styles.player} src={value.url} controls preload="metadata" />
          ) : (
            <audio className={styles.audio} src={value.url} controls preload="metadata" />
          )}
          <button type="button" className={styles.removeBtn} onClick={handleRemove} title="Удалить">
            ✕
          </button>
        </div>
      ) : (
        <div
          className={`${styles.dropzone} ${isDisabled ? styles.uploading : ''}`}
          onClick={isDisabled ? undefined : () => inputRef.current?.click()}
          role="button"
          tabIndex={isDisabled ? -1 : 0}
          aria-disabled={isDisabled}
          onKeyDown={(e) => !isDisabled && e.key === 'Enter' && inputRef.current?.click()}
        >
          {configLoading ? (
            <span className={styles.hint}>Загрузка настроек…</span>
          ) : uploading ? (
            <span className={styles.hint}>Загружается…</span>
          ) : (
            <>
              <span className={styles.icon}>🎬</span>
              <span className={styles.hint}>Нажмите, чтобы выбрать аудио или видео</span>
              <span className={styles.sub}>MP3, M4A, AAC, OGG, MP4, WebM · макс. {maxMb} МБ</span>
            </>
          )}
        </div>
      )}

      {error && <span className={styles.error} role="alert">{error}</span>}

      <input
        ref={inputRef}
        type="file"
        accept="audio/mpeg,audio/mp4,audio/aac,audio/ogg,video/mp4,video/webm"
        className={styles.hiddenInput}
        onChange={(e) => handleFile(e.target.files[0])}
        disabled={isDisabled}
      />
    </div>
  );
}
