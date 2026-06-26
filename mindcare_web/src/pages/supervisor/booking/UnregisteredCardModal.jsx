import { useState } from 'react';
import Modal from '../../../components/Modal/Modal';
import Button from '../../../components/UI/Button/Button';
import Checkbox from '../../../components/UI/Checkbox/Checkbox';
import DateInput from '../../../components/UI/DateInput/DateInput';
import { createUnregisteredStudentCard } from '../../../api/supervisor.api';
import { formatPhoneInput, PHONE_PLACEHOLDER } from '../../../features/admin/users/phone';
import styles from './UnregisteredCardModal.module.css';

const CONSENT_LABEL =
  'Подтверждаю, что субъект персональных данных дал согласие на их обработку ' +
  'при личном обращении.';

const EMPTY = {
  full_name: '',
  phone: '',
  email: '',
  birth_date: '',
  primary_concern: '',
  comment: '',
  consent: false,
};

function todayIso() {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

/**
 * Модалка создания карточки незарегистрированного студента.
 * onCreated(card) вызывается после успешного POST; родитель выбирает карточку
 * как текущего клиента и закрывает модалку.
 */
export default function UnregisteredCardModal({ open, onClose, onCreated }) {
  const [values, setValues] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  function field(name, value) {
    setValues((prev) => ({ ...prev, [name]: value }));
    setFormError(null);
  }

  function handleClose() {
    if (submitting) return;
    setValues(EMPTY);
    setFormError(null);
    onClose();
  }

  const canSubmit = values.full_name.trim() !== '' && values.consent && !submitting;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setFormError(null);
    // PII не логируется.
    try {
      const card = await createUnregisteredStudentCard({
        full_name: values.full_name.trim(),
        phone: values.phone.trim() || null,
        email: values.email.trim() || null,
        birth_date: values.birth_date || null,
        primary_concern: values.primary_concern.trim() || null,
        comment: values.comment.trim() || null,
        personal_data_consent: true,
        consent_source: 'in_person',
      });
      setValues(EMPTY);
      onCreated(card);
    } catch (err) {
      setFormError(err.message || 'Не удалось создать карточку');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={handleClose} ariaLabel="Новая карточка" zIndex={2200}>
      <div className={styles.body}>
        <h2 className={styles.title}>Новая карточка</h2>

        <form onSubmit={handleSubmit} noValidate>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="ucm-full_name">
              ФИО <span className={styles.req}>*</span>
            </label>
            <input
              id="ucm-full_name"
              className={styles.input}
              type="text"
              value={values.full_name}
              onChange={(e) => field('full_name', e.target.value)}
              placeholder="Иванов Иван Иванович"
              autoComplete="off"
              maxLength={255}
            />
          </div>

          <div className={styles.row}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="ucm-phone">Телефон</label>
              <input
                id="ucm-phone"
                className={styles.input}
                type="tel"
                value={values.phone}
                onChange={(e) => field('phone', formatPhoneInput(e.target.value))}
                placeholder={PHONE_PLACEHOLDER}
                autoComplete="off"
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="ucm-email">Email</label>
              <input
                id="ucm-email"
                className={styles.input}
                type="email"
                value={values.email}
                onChange={(e) => field('email', e.target.value)}
                placeholder="name@example.com"
                autoComplete="off"
                maxLength={255}
              />
            </div>
          </div>

          <div className={styles.field}>
            <DateInput
              id="ucm-birth_date"
              label="Дата рождения"
              value={values.birth_date}
              max={todayIso()}
              onChange={(v) => field('birth_date', v)}
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="ucm-primary_concern">Запрос</label>
            <input
              id="ucm-primary_concern"
              className={styles.input}
              type="text"
              value={values.primary_concern}
              onChange={(e) => field('primary_concern', e.target.value)}
              placeholder="Например: тревожность"
              autoComplete="off"
              maxLength={2000}
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="ucm-comment">Комментарий</label>
            <textarea
              id="ucm-comment"
              className={`${styles.input} ${styles.textarea}`}
              value={values.comment}
              onChange={(e) => field('comment', e.target.value)}
              placeholder="Необязательно"
              rows={3}
              maxLength={2000}
            />
          </div>

          <div className={styles.field}>
            <Checkbox
              id="ucm-consent"
              checked={values.consent}
              onChange={(checked) => field('consent', checked)}
              label={CONSENT_LABEL}
            />
          </div>

          {formError && (
            <div className={styles.formError} role="alert">{formError}</div>
          )}

          <div className={styles.actions}>
            <Button variant="secondary" onClick={handleClose} disabled={submitting}>
              Отмена
            </Button>
            <Button variant="primary" type="submit" disabled={!canSubmit}>
              {submitting ? 'Создаём…' : 'Создать карточку'}
            </Button>
          </div>
        </form>
      </div>
    </Modal>
  );
}
