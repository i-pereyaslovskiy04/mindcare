import { useEffect, useState } from 'react';
import Modal from '../../../../components/Modal/Modal';
import TiptapEditor from '../../../../components/UI/TiptapEditor/TiptapEditor';
import ImageUpload from '../../../../components/UI/ImageUpload/ImageUpload';
import MultiSelect from '../../../../components/UI/MultiSelect/MultiSelect';
import ContentPreview from '../../../../components/UI/ContentPreview/ContentPreview';
import Button from '../../../../components/UI/Button/Button';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import DateInput, { isoToDateOnly, dateOnlyToPublishedAtIso } from '../../../../components/UI/DateInput';
import { publishCheckboxLabel, submitButtonLabel } from '../../publishLabels';
import { getTagsPublic } from '../../../../api/tags.api';
import {
  getAdminCategories, getPublicCategories, createArticle, updateArticle,
  createMyArticle, updateMyArticle,
} from '../../../../api/articles.api';
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

// mode: 'admin' — полная форма администратора (публикация, дата);
// 'author' — своя статья автора (ADR-034): только содержание, сохраняется
// черновиком; публичные категории (админский endpoint автору недоступен).
// authorRole: 'psychologist' — публикует проверяющий после отправки;
// 'supervisor' — публикует сам из списка (Дополнение 2026-10-28).
const MODES = {
  admin:  { loadCategories: getAdminCategories, create: createArticle, update: updateArticle, publishing: true },
  author: { loadCategories: getPublicCategories, create: createMyArticle, update: updateMyArticle, publishing: false },
};

const AUTHOR_HINTS = {
  psychologist: {
    draft: 'Материал сохранится черновиком. Чтобы опубликовать, отправьте его на проверку супервизору.',
    published: 'Материал опубликован. Сохранение снимет его с публикации - после правки отправьте его на проверку снова.',
  },
  supervisor: {
    draft: 'Материал сохранится черновиком. Опубликовать его можно кнопкой «Опубликовать» в списке.',
    published: 'Материал опубликован. Сохранение снимет его с публикации - после правки опубликуйте его снова.',
  },
};

export default function ArticleFormModal({
  open, article, onClose, onSaved, mode = 'admin', authorRole = 'psychologist',
}) {
  const isEdit = Boolean(article);
  const cfg = MODES[mode] || MODES.admin;
  const hints = AUTHOR_HINTS[authorRole] || AUTHOR_HINTS.psychologist;
  // API автора выбирается ролью; админские вызовы — с прежними аргументами.
  const authorArgs = mode === 'author' ? [authorRole] : [];
  const editingPublished = mode === 'author' && isEdit && article?.status === 'published';
  const [form, setForm]                 = useState(EMPTY);
  const [tagOptions, setTagOptions]     = useState([]);
  const [catOptions, setCatOptions]     = useState([]);
  const [catLoadError, setCatLoadError] = useState('');
  const [errors, setErrors]             = useState({});
  const [submitting, setSubmitting]     = useState(false);
  const [previewOpen, setPreviewOpen]   = useState(false);
  // formReady — TiptapEditor рендерится только после заполнения формы данными.
  // ВАЖНО: работает при условном монтировании ({article && <ArticleFormModal/>}).
  const [formReady, setFormReady]       = useState(false);

  useEffect(() => {
    Promise.all([getTagsPublic(), cfg.loadCategories()])
      .then(([tags, cats]) => {
        setTagOptions((tags || []).map(t => ({ value: t.uuid, label: t.name })));
        setCatOptions((cats || []).map(c => ({ value: c.id, label: c.name })));
        setCatLoadError('');
      })
      .catch(() => setCatLoadError('Не удалось загрузить типы материалов'));
  }, [cfg]);

  useEffect(() => {
    if (!open) return;
    if (isEdit && article) {
      setForm({
        title:       article.title || '',
        excerpt:     article.excerpt || '',
        content:     article.content || '',
        cover:       article.cover_image_url ? { uuid: article.cover_image_uuid || null, url: article.cover_image_url } : null,
        categoryIds: article.categories?.map(c => c.id) || [],
        tagUuids:    article.tags?.map(t => t.uuid) || [],
        isPublished: article.is_published || false,
        publishedAt: isoToDateOnly(article.published_at),
      });
    } else {
      setForm(EMPTY);
    }
    setErrors({});
    setFormReady(true);
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
        ...(cfg.publishing ? {
          is_published: form.isPublished,
          published_at: dateOnlyToPublishedAtIso(form.publishedAt),
        } : {}),
      };
      const saved = isEdit
        ? await cfg.update(article.uuid, payload, ...authorArgs)
        : await cfg.create(payload, ...authorArgs);
      onSaved(saved);
    } catch (err) {
      setErrors({ _form: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Modal open={open} onClose={onClose} wide>
        <form onSubmit={handleSubmit} className={styles.form}>
          <h2 className={styles.modalTitle}>{isEdit ? 'Редактировать материал' : 'Новый материал'}</h2>
          {mode === 'author' && (
            <p className={editingPublished ? styles.notice : styles.hint}>
              {editingPublished ? hints.published : hints.draft}
            </p>
          )}

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

          {cfg.publishing && (
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
                label={publishCheckboxLabel()}
              />
            </div>
          </div>
          )}

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
              {cfg.publishing
                ? submitButtonLabel({ isEdit, isPublished: form.isPublished, submitting })
                : (submitting ? 'Сохранение…' : 'Сохранить черновик')}
            </Button>
          </div>
        </form>
      </Modal>

      {previewOpen && (
        <ContentPreview
          open
          onClose={() => setPreviewOpen(false)}
          title={form.title}
          excerpt={form.excerpt}
          content={form.content}
          coverUrl={form.cover?.url || null}
          tags={tagOptions.filter(t => form.tagUuids.includes(t.value)).map(t => t.label)}
          categories={catOptions.filter(c => form.categoryIds.includes(c.value)).map(c => c.label)}
          publishedAt={dateOnlyToPublishedAtIso(form.publishedAt)}
        />
      )}
    </>
  );
}
