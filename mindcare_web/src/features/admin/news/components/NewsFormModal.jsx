import { useEffect, useState } from 'react';
import Modal from '../../../../components/Modal/Modal';
import TiptapEditor from '../../../../components/UI/TiptapEditor/TiptapEditor';
import ImageUpload from '../../../../components/UI/ImageUpload/ImageUpload';
import MultiSelect from '../../../../components/UI/MultiSelect/MultiSelect';
import { getTagsPublic } from '../../../../api/tags.api';
import { createNews, updateNews } from '../../../../api/news.api';
import styles from './NewsFormModal.module.css';

const EMPTY = {
  title: '',
  content: '',
  cover: null,       // { uuid, url } | null
  tagUuids: [],
  isPublished: false,
  publishedAt: '',
};

export default function NewsFormModal({ open, news, onClose, onSaved }) {
  const isEdit = Boolean(news);
  const [form, setForm]         = useState(EMPTY);
  const [tagOptions, setTagOptions] = useState([]);
  const [errors, setErrors]     = useState({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getTagsPublic().then(data => {
      setTagOptions((data || []).map(t => ({ value: t.uuid, label: t.name })));
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!open) return;
    if (isEdit && news) {
      setForm({
        title:       news.title || '',
        content:     news.content || '',
        cover:       news.cover_image_url ? { uuid: null, url: news.cover_image_url } : null,
        tagUuids:    news.tags?.map(t => t.uuid) || [],
        isPublished: news.is_published || false,
        publishedAt: news.published_at ? news.published_at.slice(0, 16) : '',
      });
    } else {
      setForm(EMPTY);
    }
    setErrors({});
  }, [open, isEdit, news]);

  function set(field, value) {
    setForm(prev => ({ ...prev, [field]: value }));
    setErrors(prev => ({ ...prev, [field]: undefined, _form: undefined }));
  }

  function validate() {
    const errs = {};
    if (!form.title.trim()) errs.title = 'Введите заголовок';
    return errs;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    if (submitting) return;
    setSubmitting(true);
    try {
      const payload = {
        title:            form.title.trim(),
        content:          form.content || null,
        cover_image_uuid: form.cover?.uuid || null,
        tag_uuids:        form.tagUuids,
        is_published:     form.isPublished,
        published_at:     form.publishedAt ? new Date(form.publishedAt).toISOString() : null,
      };
      const saved = isEdit
        ? await updateNews(news.uuid, payload)
        : await createNews(payload);
      onSaved(saved);
    } catch (err) {
      setErrors({ _form: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose}>
      <form onSubmit={handleSubmit} className={styles.form}>
        <h2 className={styles.modalTitle}>{isEdit ? 'Редактировать новость' : 'Новая новость'}</h2>
        <div className={styles.field}>
          <label className={styles.label}>Заголовок *</label>
          <input
            className={`${styles.input} ${errors.title ? styles.inputError : ''}`}
            value={form.title}
            onChange={e => set('title', e.target.value)}
            placeholder="Введите заголовок"
            maxLength={255}
          />
          {errors.title && <span className={styles.hint} role="alert">{errors.title}</span>}
        </div>

        <div className={styles.field}>
          <label className={styles.label}>Содержимое</label>
          <TiptapEditor
            key={news?.uuid || 'create'}
            value={form.content}
            onChange={val => set('content', val)}
          />
        </div>

        <div className={styles.field}>
          <ImageUpload
            value={form.cover}
            onChange={val => set('cover', val)}
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label}>Теги</label>
          <MultiSelect
            options={tagOptions}
            value={form.tagUuids}
            onChange={vals => set('tagUuids', vals)}
            placeholder="Выберите теги..."
          />
        </div>

        <div className={styles.row}>
          <div className={styles.field}>
            <label className={styles.label}>Дата публикации</label>
            <input
              type="datetime-local"
              className={styles.input}
              value={form.publishedAt}
              onChange={e => set('publishedAt', e.target.value)}
            />
          </div>
          <div className={styles.fieldCheck}>
            <label className={styles.checkLabel}>
              <input
                type="checkbox"
                checked={form.isPublished}
                onChange={e => set('isPublished', e.target.checked)}
              />
              Опубликовать
            </label>
          </div>
        </div>

        {errors._form && (
          <div className={styles.formError} role="alert">{errors._form}</div>
        )}

        <div className={styles.actions}>
          <button type="button" className={styles.btnCancel} onClick={onClose} disabled={submitting}>
            Отмена
          </button>
          <button type="submit" className={styles.btnSubmit} disabled={submitting}>
            {submitting ? 'Сохранение…' : isEdit ? 'Сохранить' : 'Создать'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
