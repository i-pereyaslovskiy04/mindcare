import { useEffect, useRef, useState } from 'react';
import { uploadImage } from '../../../api/media.api';
import styles from './ImageUpload.module.css';

// Единый источник лимита — backend GET /api/public/config.
// Module-level promise: конфиг запрашивается один раз и переиспользуется между монтированиями.
// После изменения NEWS_IMAGE_MAX_SIZE_MB достаточно перезапустить backend и обновить страницу —
// пересборка React не нужна.
let _configPromise = null;
function fetchServerConfig() {
  if (!_configPromise) {
    _configPromise = fetch('/api/public/config')
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
      .catch(() => null); // null сигнализирует об ошибке — см. обработку в компоненте
  }
  return _configPromise;
}

export default function ImageUpload({ value, onChange, label = 'Обложка' }) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  // null = конфиг ещё не загружен; число = лимит получен с backend
  const [maxFileMb, setMaxFileMb] = useState(null);

  useEffect(() => {
    fetchServerConfig().then(cfg => {
      setMaxFileMb(cfg?.newsImageMaxSizeMb ?? 20);
    });
  }, []);

  const configLoading = maxFileMb === null;

  async function handleFile(file) {
    if (!file || configLoading) return;
    setError('');

    if (file.size > maxFileMb * 1024 * 1024) {
      setError(`Файл превышает ${maxFileMb} МБ`);
      return;
    }

    setUploading(true);
    try {
      const result = await uploadImage(file);
      onChange({ uuid: result.uuid, url: result.url });
    } catch (err) {
      setError(err.message || 'Ошибка загрузки');
    } finally {
      setUploading(false);
    }
  }

  function handleChange(e) {
    handleFile(e.target.files[0]);
  }

  function handleDrop(e) {
    e.preventDefault();
    handleFile(e.dataTransfer.files[0]);
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
          <img src={value.url} alt="Обложка" className={styles.img} />
          <button type="button" className={styles.removeBtn} onClick={handleRemove} title="Удалить">
            ✕
          </button>
        </div>
      ) : (
        <div
          className={`${styles.dropzone} ${isDisabled ? styles.uploading : ''}`}
          onDragOver={e => e.preventDefault()}
          onDrop={isDisabled ? undefined : handleDrop}
          onClick={isDisabled ? undefined : () => inputRef.current?.click()}
          role="button"
          tabIndex={isDisabled ? -1 : 0}
          aria-disabled={isDisabled}
          onKeyDown={e => !isDisabled && e.key === 'Enter' && inputRef.current?.click()}
        >
          {configLoading ? (
            <span className={styles.hint}>Загрузка настроек…</span>
          ) : uploading ? (
            <span className={styles.hint}>Загружается…</span>
          ) : (
            <>
              <span className={styles.icon}>🖼</span>
              <span className={styles.hint}>Нажмите или перетащите изображение</span>
              <span className={styles.sub}>JPEG, PNG, WebP · макс. {maxFileMb} МБ</span>
            </>
          )}
        </div>
      )}

      {error && <span className={styles.error} role="alert">{error}</span>}

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className={styles.hiddenInput}
        onChange={handleChange}
        disabled={isDisabled}
      />
    </div>
  );
}
