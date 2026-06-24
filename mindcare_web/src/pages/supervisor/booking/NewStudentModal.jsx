import { useState } from 'react';
import Modal from '../../../components/Modal/Modal';
import Button from '../../../components/UI/Button/Button';
import Checkbox from '../../../components/UI/Checkbox/Checkbox';
import { createSupervisorStudent } from '../../../api/supervisor.api';
import styles from './NewStudentModal.module.css';

const CONSENT_LABEL =
  'Подтверждаю, что студент лично дал согласие на обработку персональных данных ' +
  '(получено очно).';

const EMPTY = {
  full_name: '',
  email: '',
  phone: '',
  primary_concern: '',
  consent: false,
};

/**
 * Модалка создания полноценного аккаунта зарегистрированного студента
 * (admin/supervisor) прямо из раздела «Запись».
 *
 * psychologistId уже выбран на шаге 1 — студент сразу получает active engagement
 * с этим психологом и становится пригоден для записи через student_id.
 *
 * onCreated(student) вызывается при подтверждении экрана успеха; родитель
 * рефетчит engagements и выбирает созданного студента субъектом записи.
 * ПДн и временный пароль не логируются.
 */
export default function NewStudentModal({ open, psychologistId, onClose, onCreated }) {
  const [values, setValues] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);
  const [created, setCreated] = useState(null);

  function field(name, value) {
    setValues((prev) => ({ ...prev, [name]: value }));
    setFormError(null);
  }

  function handleClose() {
    if (submitting) return;
    if (created) onCreated(created);
    setValues(EMPTY);
    setCreated(null);
    setFormError(null);
    onClose();
  }

  const canSubmit =
    values.full_name.trim() !== '' &&
    values.email.trim() !== '' &&
    values.consent &&
    !submitting;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setFormError(null);
    // ПДн и временный пароль не логируются.
    try {
      const student = await createSupervisorStudent({
        full_name: values.full_name.trim(),
        email: values.email.trim(),
        phone: values.phone.trim() || null,
        primary_concern: values.primary_concern.trim() || null,
        psychologist_id: psychologistId ?? null,
        personal_data_consent: true,
      });
      setCreated(student);
    } catch (err) {
      setFormError(err.message || 'Не удалось создать аккаунт студента');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      ariaLabel="Новый аккаунт студента"
      zIndex={2200}
    >
      {created ? (
        <SuccessScreen student={created} onContinue={handleClose} />
      ) : (
        <div className={styles.body}>
          <h2 className={styles.title}>Новый аккаунт студента</h2>

          <form onSubmit={handleSubmit} noValidate>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="nsm-full_name">
                ФИО <span className={styles.req}>*</span>
              </label>
              <input
                id="nsm-full_name"
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
                <label className={styles.label} htmlFor="nsm-email">
                  Email <span className={styles.req}>*</span>
                </label>
                <input
                  id="nsm-email"
                  className={styles.input}
                  type="email"
                  value={values.email}
                  onChange={(e) => field('email', e.target.value)}
                  placeholder="name@example.com"
                  autoComplete="off"
                  maxLength={255}
                />
              </div>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="nsm-phone">Телефон</label>
                <input
                  id="nsm-phone"
                  className={styles.input}
                  type="tel"
                  value={values.phone}
                  onChange={(e) => field('phone', e.target.value)}
                  placeholder="+7…"
                  autoComplete="off"
                  maxLength={50}
                />
              </div>
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="nsm-primary_concern">Запрос</label>
              <input
                id="nsm-primary_concern"
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
              <Checkbox
                id="nsm-consent"
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
                {submitting ? 'Создаём…' : 'Создать аккаунт'}
              </Button>
            </div>
          </form>
        </div>
      )}
    </Modal>
  );
}

function SuccessScreen({ student, onContinue }) {
  return (
    <div className={styles.body}>
      <div className={styles.successIcon} aria-hidden="true">✓</div>
      <h2 className={styles.title}>Аккаунт студента создан</h2>
      <p className={styles.successName}>{student.full_name}</p>
      <p className={styles.successEmail}>{student.email}</p>

      <div className={styles.passwordBlock}>
        <p className={styles.passwordLabel}>Временный пароль</p>
        <p className={styles.password}>{student.temporary_password}</p>
        <p className={styles.passwordNote}>
          Пароль также отправлен на email студента.
        </p>
      </div>

      <div className={styles.actions}>
        <Button variant="primary" onClick={onContinue}>
          Выбрать студента и продолжить
        </Button>
      </div>
    </div>
  );
}
