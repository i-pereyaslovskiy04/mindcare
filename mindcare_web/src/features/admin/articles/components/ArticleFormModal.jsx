import { useEffect, useState } from 'react';
import Modal from '../../../../components/Modal/Modal';
import TiptapEditor from '../../../../components/UI/TiptapEditor/TiptapEditor';
import ImageUpload from '../../../../components/UI/ImageUpload/ImageUpload';
import MultiSelect from '../../../../components/UI/MultiSelect/MultiSelect';
import { getTagsPublic } from '../../../../api/tags.api';
import { getAdminCategories, createArticle, updateArticle } from '../../../../api/articles.api';
import styles from './ArticleFormModal.module.css';

const EMPTY = {
  title: '',
  excerpt: '',
  content: '',
  cover: null,
  categoryIds: [],
  tagUuids: [],
  isPublished: false,
  publishedAt: '',
};

export default function ArticleFormModal({ open, article, onClose, onSaved }) {
  const isEdit = Boolean(article);
  const [form, setForm]           = useState(EMPTY);
  const [tagOptions, setTagOptions]   = useState([]);
  const [catOptions, setCatOptions]   = useState([]);
  const [catLoadError, setCatLoadError] = useState('');
  const [errors, setErrors]       = useState({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    Promise.all([getTagsPublic(), getAdminCategories()])
      .then(([tags, cats]) => {
        setTagOptions((tags || []).map(t => ({ value: t.uuid, label: t.name })));
        setCatOptions((cats || []).map(c => ({ value: c.id, label: c.name })));
        setCatLoadError('');
      })
      .catch(() => setCatLoadError('Не удалось загрузить типы материалов'));
  }, []);

  useEffect(() => {
    if (!open) return;
    if (isEdit && article) {
      setForm({
        title:       article.title || '',
        excerpt:     article.excerpt || '',
        content:     article.content || '',
        cover:       article.cover_image_url ? { uuid: null, url: article.cover_image_url } : null,
        categoryIds: article.categories?.map(c => c.id) || [],
        tagUuids:    article.tags?.map(t => t.uuid) || [],
        isPublished: article.is_published || false,
        publishedAt: article.published_at ? article.published_at.slice(0, 16) : '',
      });
    } else {
      setForm(EMPTY);
    }
    setErrors({});
  }, [open, isEdit, article]);

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
        excerpt:          form.excerpt.trim() || null,
        content:          form.content || null,
        cover_image_uuid: form.cover?.uuid || null,
        category_ids:     form.categoryIds,
        tag_uuids:        form.tagUuids,
        is_published:     form.isPublished,
        published_at:     form.publishedAt ? new Date(form.publishedAt).toISOString() : null,
      };
      const saved = isEdit
        ? await updateArticle(article.uuid, payload)
        : await createArticle(payload);
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
        <h2 className={styles.modalTitle}>{isEdit ? 'Редактировать материал' : 'Новый материал'}</h2>

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
          <label className={styles.label}>Краткое описание</label>
          <textarea
            className={styles.textarea}
            value={form.excerpt}
            onChange={e => set('excerpt', e.target.value)}
            placeholder="Пара предложений для карточки материала"
            rows={2}
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label}>Содержимое</label>
          <TiptapEditor
            key={article?.uuid || 'create'}
            value={form.content}
            onChange={val => set('content', val)}
          />
        </div>

        <div className={styles.field}>
          <ImageUpload value={form.cover} onChange={val => set('cover', val)} />
        </div>

        <div className={styles.row2}>
          <div className={styles.field}>
            <label className={styles.label}>Тип (категория)</label>
            <MultiSelect
              options={catOptions}
              value={form.categoryIds}
              onChange={vals => set('categoryIds', vals)}
              placeholder="Выберите тип..."
            />
            {catLoadError && (
              <span className={styles.hint} role="alert">{catLoadError}</span>
            )}
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Теги (темы)</label>
            <MultiSelect
              options={tagOptions}
              value={form.tagUuids}
              onChange={vals => set('tagUuids', vals)}
              placeholder="Выберите теги..."
            />
          </div>
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
