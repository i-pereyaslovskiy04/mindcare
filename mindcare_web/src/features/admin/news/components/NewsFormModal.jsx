import { useEffect, useState } from 'react';
import Modal from '../../../../components/Modal/Modal';
import TiptapEditor from '../../../../components/UI/TiptapEditor/TiptapEditor';
import ImageUpload from '../../../../components/UI/ImageUpload/ImageUpload';
import MultiSelect from '../../../../components/UI/MultiSelect/MultiSelect';
import ContentPreview from '../../../../components/UI/ContentPreview/ContentPreview';
import Button from '../../../../components/UI/Button/Button';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import DateInput, { isoToDateOnly, dateOnlyToPublishedAtIso } from '../../../../components/UI/DateInput';
import { getTagsPublic } from '../../../../api/tags.api';
import { createNews, updateNews } from '../../../../api/news.api';
import styles from './NewsFormModal.module.css';

const EMPTY = {
  title: '',
  content: '',
  cover: null,
  tagUuids: [],
  isPublished: false,
  publishedAt: '',
};

export default function NewsFormModal({ open, news, onClose, onSaved }) {
  const isEdit = Boolean(news);
  const [form, setForm]             = useState(EMPTY);
  const [tagOptions, setTagOptions] = useState([]);
  const [errors, setErrors]         = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  // formReady — TiptapEditor рендерится только после заполнения формы данными.
  // Гарантирует монтирование редактора с правильным content.
  // ВАЖНО: работает при условном монтировании модалки ({editTarget && <Modal/>}).
  // При persistent-mount паттерне formReady нужно сбрасывать вручную в false.
  const [formReady, setFormReady] = useState(false);

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
        cover:       news.cover_image_url ? { uuid: news.cover_image_uuid || null, url: news.cover_image_url } : null,
        tagUuids:    news.tags?.map(t => t.uuid) || [],
        isPublished: news.is_published || false,
        publishedAt: isoToDateOnly(news.published_at),
      });
    } else {
      setForm(EMPTY);
    }
    setErrors({});
    // setForm и setFormReady батчатся React 18 в один рендер.
    // TiptapEditor появится впервые уже с нужным form.content.
    setFormReady(true);
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
        published_at:     dateOnlyToPublishedAtIso(form.publishedAt),
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

  const selectedTagNames = tagOptions
    .filter(t => form.tagUuids.includes(t.value))
    .map(t => t.label);

  return (
    <>
      <Modal open={open} onClose={onClose} wide>
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
            {/* Скелетон показывается пока форма не готова.
                Когда formReady станет true, React заменит его на TiptapEditor
                уже с нужным content — без промежуточного пустого состояния. */}
            {formReady ? (
              <TiptapEditor
                value={form.content}
                onChange={val => set('content', val)}
              />
            ) : (
              <div className={styles.editorSkeleton} />
            )}
          </div>

          <div className={styles.field}>
            <ImageUpload value={form.cover} onChange={val => set('cover', val)} />
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
              <DateInput
                label="Дата публикации"
                value={form.publishedAt}
                onChange={val => set('publishedAt', val)}
              />
            </div>
            <div className={styles.fieldCheck}>
              <Checkbox
                checked={form.isPublished}
                onChange={(val) => set('isPublished', val)}
                label="Опубликовать"
              />
            </div>
          </div>

          {errors._form && (
            <div className={styles.formError} role="alert">{errors._form}</div>
          )}

          <div className={styles.actions}>
            <Button variant="secondary" onClick={onClose} disabled={submitting}>
              Отмена
            </Button>
            <Button variant="ghost" onClick={() => setPreviewOpen(true)}>
              Предпросмотр
            </Button>
            <Button variant="primary" type="submit" disabled={submitting}>
              {submitting ? 'Сохранение…' : isEdit ? 'Сохранить' : 'Создать'}
            </Button>
          </div>
        </form>
      </Modal>

      {previewOpen && (
        <ContentPreview
          open
          onClose={() => setPreviewOpen(false)}
          title={form.title}
          content={form.content}
          coverUrl={form.cover?.url || null}
          tags={selectedTagNames}
          publishedAt={dateOnlyToPublishedAtIso(form.publishedAt)}
        />
      )}
    </>
  );
}
