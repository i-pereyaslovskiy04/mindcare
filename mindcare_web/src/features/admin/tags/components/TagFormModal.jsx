import { useState, useEffect } from 'react';
import Modal from '../../../../components/Modal/Modal';
import { createTag, updateTag } from '../../../../api/tags.api';
import Button from '../../../../components/UI/Button/Button';
import styles from './TagFormModal.module.css';

export default function TagFormModal({ mode, tag, onSuccess, onClose }) {
  const isEdit = mode === 'edit';

  const [name, setName]             = useState('');
  const [error, setError]           = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setName(isEdit && tag ? tag.name : '');
    setError('');
  }, [isEdit, tag]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (submitting) return;

    const trimmed = name.trim();
    if (!trimmed) {
      setError('Введите название темы');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      if (isEdit) await updateTag(tag.uuid, { name: trimmed });
      else        await createTag({ name: trimmed });
      onSuccess?.();
    } catch (err) {
      setError(err.message || 'Произошла ошибка');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open onClose={onClose}>
      <div className={styles.body}>
        <h2 className={styles.title}>
          {isEdit ? 'Переименовать тему' : 'Новая тема'}
        </h2>

        <form onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="tag-name">
              Название
            </label>
            <input
              id="tag-name"
              className={styles.input}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="например: Тревога"
              autoFocus
              maxLength={100}
            />
            <span className={styles.hint}>
              Первая буква будет заглавной, остальные — строчными
            </span>
          </div>

          {error && <p className={styles.formError}>{error}</p>}

          <div className={styles.footer}>
            <Button variant="secondary" onClick={onClose} disabled={submitting}>
              Отмена
            </Button>
            <Button variant="primary" type="submit" disabled={submitting}>
              {submitting ? 'Сохранение...' : isEdit ? 'Сохранить' : 'Создать'}
            </Button>
          </div>
        </form>
      </div>
    </Modal>
  );
}
