import { useRef, useState } from 'react';
import { uploadImage } from '../../../api/media.api';
import styles from './ImageUpload.module.css';

export default function ImageUpload({ value, onChange, label = 'Обложка' }) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  async function handleFile(file) {
    if (!file) return;
    setError('');
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
          className={`${styles.dropzone} ${uploading ? styles.uploading : ''}`}
          onDragOver={e => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={e => e.key === 'Enter' && inputRef.current?.click()}
        >
          {uploading ? (
            <span className={styles.hint}>Загружается…</span>
          ) : (
            <>
              <span className={styles.icon}>🖼</span>
              <span className={styles.hint}>Нажмите или перетащите изображение</span>
              <span className={styles.sub}>JPEG, PNG, GIF, WebP · макс. 5 МБ</span>
            </>
          )}
        </div>
      )}

      {error && <span className={styles.error} role="alert">{error}</span>}

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp"
        className={styles.hiddenInput}
        onChange={handleChange}
      />
    </div>
  );
}
