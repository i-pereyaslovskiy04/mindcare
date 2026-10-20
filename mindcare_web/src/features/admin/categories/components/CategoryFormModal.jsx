import { useEffect, useState } from 'react';
import Modal from '../../../../components/Modal/Modal';
import { createCategory, updateCategory } from '../../../../api/categories.api';
import Button from '../../../../components/UI/Button/Button';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import styles from './CategoryFormModal.module.css';

const EMPTY = {
  name: '',
  slug: '',
  description: '',
  display_order: 0,
  is_active: true,
};

export default function CategoryFormModal({ open, category, onClose, onSaved }) {
  const isEdit = Boolean(category);

  const [form, setForm]             = useState(EMPTY);
  const [errors, setErrors]         = useState({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (isEdit && category) {
      setForm({
        name:          category.name || '',
        slug:          category.slug || '',
        description:   category.description || '',
        display_order: category.display_order ?? 0,
        is_active:     category.is_active ?? true,
      });
    } else {
      setForm(EMPTY);
    }
    setErrors({});
  }, [open, isEdit, category]);

  function set(field, value) {
    setForm(prev => ({ ...prev, [field]: value }));
    setErrors(prev => ({ ...prev, [field]: undefined, _form: undefined }));
  }

  function validate() {
    const errs = {};
    if (!form.name.trim()) errs.name = 'Введите название';
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
        name:          form.name.trim(),
        slug:          form.slug.trim(),
        description:   form.description.trim() || null,
        display_order: Number(form.display_order) || 0,
        is_active:     form.is_active,
      };

      const saved = isEdit
        ? await updateCategory(category.id, payload)
        : await createCategory(payload);
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
        <h2 className={styles.modalTitle}>
          {isEdit ? 'Редактировать тип материалов' : 'Новый тип материалов'}
        </h2>

        <div className={styles.field}>
          <label className={styles.label}>Название *</label>
          <input
            className={`${styles.input} ${errors.name ? styles.inputError : ''}`}
            value={form.name}
            onChange={e => set('name', e.target.value)}
            placeholder="Например: Управление тревогой"
            maxLength={100}
          />
          {errors.name && (
            <span className={styles.hint} role="alert">{errors.name}</span>
          )}
        </div>

        <div className={styles.field}>
          <label className={styles.label}>
            Slug{' '}
            <span className={styles.labelHint}>
              (оставьте пустым — сгенерируется автоматически)
            </span>
          </label>
          <input
            className={`${styles.input} ${errors.slug ? styles.inputError : ''}`}
            value={form.slug}
            onChange={e => set('slug', e.target.value)}
            placeholder="upravlenie-trevozhnostyu"
            maxLength={100}
          />
          {errors.slug && (
            <span className={styles.hint} role="alert">{errors.slug}</span>
          )}
        </div>

        <div className={styles.field}>
          <label className={styles.label}>Описание</label>
          <textarea
            className={styles.textarea}
            value={form.description}
            onChange={e => set('description', e.target.value)}
            placeholder="Краткое описание типа материалов"
            rows={2}
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label}>Порядок отображения</label>
          <input
            type="number"
            className={`${styles.input} ${styles.inputOrder}`}
            value={form.display_order}
            onChange={e => set('display_order', e.target.value)}
            min={0}
            max={9999}
          />
        </div>

        <div className={styles.fieldCheck}>
          <Checkbox
            checked={form.is_active}
            onChange={(val) => set('is_active', val)}
            label="Активна (показывать в формах добавления материалов)"
          />
        </div>

        {errors._form && (
          <div className={styles.formError} role="alert">{errors._form}</div>
        )}

        <div className={styles.actions}>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Отмена
          </Button>
          <Button variant="primary" type="submit" disabled={submitting}>
            {submitting ? 'Сохранение…' : isEdit ? 'Сохранить' : 'Создать'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
