import { useId, useRef, useState } from 'react';
import Button from '../../../components/UI/Button/Button';
import DateInput from '../../../components/UI/DateInput/DateInput';
import MaterialPicker from './MaterialPicker';
import styles from './AssignmentForm.module.css';

export const TEXT_MAX = 4000;

/**
 * Форма выдачи задания: текст (подпись, счётчик), необязательный срок,
 * необязательный материал из библиотеки (встроенная панель выбора).
 * Используется разделом «Задания» карточки клиента и быстрым диалогом в списке
 * студентов. onCreate({ text, dueDate, articleUuid }) → Promise<boolean>;
 * при успехе форма очищается. bare — без собственной рамки (внутри диалога).
 */
export default function AssignmentForm({
  onCreate, submitting, formError, title = 'Новое задание', bare = false,
  submitLabel = 'Выдать задание',
}) {
  const formId = useId();
  const textId = `${formId}-text`;
  const counterId = `${formId}-counter`;
  const errorId = `${formId}-error`;
  const dueLabelId = `${formId}-due`;
  const [text, setText] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [material, setMaterial] = useState(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const pickerTriggerRef = useRef(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (submitting) return;
    const ok = await onCreate({ text, dueDate, articleUuid: material?.uuid });
    if (ok) {
      setText('');
      setDueDate('');
      setMaterial(null);
      setPickerOpen(false);
    }
  }

  function closePicker() {
    setPickerOpen(false);
    requestAnimationFrame(() => pickerTriggerRef.current?.focus());
  }

  const textInvalid = formError?.field === 'text';
  const describedBy = [counterId, formError ? errorId : null].filter(Boolean).join(' ');

  return (
    <form className={bare ? `${styles.form} ${styles.bare}` : styles.form} onSubmit={handleSubmit} noValidate>
      {title && <h4 className={styles.formTitle}>{title}</h4>}

      <label htmlFor={textId} className={styles.label}>Текст задания</label>
      <textarea
        id={textId}
        className={styles.textarea}
        value={text}
        onChange={e => setText(e.target.value)}
        maxLength={TEXT_MAX}
        rows={4}
        required
        aria-invalid={textInvalid || undefined}
        aria-describedby={describedBy}
        disabled={submitting}
      />
      <p id={counterId} className={styles.counter}>{text.length} / {TEXT_MAX}</p>

      <div className={styles.row}>
        <div className={styles.field}>
          <span id={dueLabelId} className={styles.label}>Срок (необязательно)</span>
          <DateInput
            value={dueDate}
            onChange={setDueDate}
            labelledBy={dueLabelId}
            disabled={submitting}
          />
          {dueDate && (
            <button type="button" className={styles.linkBtn} onClick={() => setDueDate('')}>
              Убрать срок
            </button>
          )}
        </div>

        <div className={styles.field}>
          <span className={styles.label}>Материал (необязательно)</span>
          {material ? (
            <div className={styles.chosen}>
              <span className={styles.chosenTitle}>{material.title}</span>
              <button
                type="button"
                className={styles.linkBtn}
                onClick={() => setMaterial(null)}
                aria-label={`Убрать материал «${material.title}»`}
                disabled={submitting}
              >
                Убрать
              </button>
            </div>
          ) : (
            <Button
              ref={pickerTriggerRef}
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setPickerOpen(open => !open)}
              aria-expanded={pickerOpen}
              disabled={submitting}
            >
              Выбрать из библиотеки
            </Button>
          )}
        </div>
      </div>

      {pickerOpen && !material && (
        <MaterialPicker
          onClose={closePicker}
          onSelect={(picked) => { setMaterial(picked); setPickerOpen(false); }}
        />
      )}

      {formError && (
        <p id={errorId} className={styles.error} role="alert">{formError.message}</p>
      )}

      <div className={styles.formActions}>
        <Button type="submit" loading={submitting} disabled={!text.trim()}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
