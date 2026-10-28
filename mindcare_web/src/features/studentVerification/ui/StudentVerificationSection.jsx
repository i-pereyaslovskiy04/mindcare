import { useEffect, useId, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import Select from '../../../components/UI/Select/Select';
import TextField from '../../../components/UI/TextField/TextField';
import { submitMyVerification } from '../../../api/studentVerification.api';
import useFaculties from '../hooks/useFaculties';
import {
  STUDENT_VERIFICATION_ANCHOR,
  formatVerificationDate,
  verificationErrorMessage,
  verificationStatusLabel,
  verificationStatusTone,
} from '../lib/status';
import styles from './StudentVerificationSection.module.css';

const TICKET_MAX_LEN = 50;

/**
 * Раздел «Подтверждение студента ДонГУ» в настройках (ADR-029).
 *
 * Данные статуса приходят пропсами (их же использует бейдж в профиле), каталог
 * факультетов — с backend. Форма видна, только когда backend разрешает подачу
 * (`can_submit`): до первой заявки и после отказа. Pending неизменяема,
 * одобрение финально. Номер билета не логируется и после отправки очищается.
 * Поля — shared Select/TextField (appearance="field"): ошибка проверки
 * показывается у своего поля (aria-invalid, aria-describedby), фокус уходит
 * на первое ошибочное поле; общий блок — только для ответа сервера.
 *
 * Якорь `#student-verification` — цель ссылки из system-сообщения: после
 * загрузки раздел прокручивается в видимую область и получает фокус.
 */
export default function StudentVerificationSection({
  className,
  verification,
  loading,
  error,
  onSubmitted,
}) {
  const location = useLocation();
  const headingId = useId();
  const sectionRef = useRef(null);
  const ticketRef = useRef(null);
  const facultyId = `${headingId}-faculty`;
  const ticketId = `${headingId}-ticket`;
  const canSubmit = Boolean(verification?.can_submit);
  const faculties = useFaculties(canSubmit);

  const [faculty, setFaculty] = useState('');
  const [ticket, setTicket] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (loading || location.hash !== `#${STUDENT_VERIFICATION_ANCHOR}`) return;
    const node = sectionRef.current;
    if (!node) return;
    node.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    node.focus?.({ preventScroll: true });
  }, [location.hash, loading]);

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSuccess(false);
    const ticketNumber = ticket.trim();
    if (!faculty) {
      setFieldErrors({ faculty: 'Выберите факультет' });
      // Select не пробрасывает ref: цель фокуса — кнопка-контрол по её id.
      document.getElementById(facultyId)?.focus();
      return;
    }
    if (!ticketNumber) {
      setFieldErrors({ ticket: 'Укажите номер студенческого билета' });
      ticketRef.current?.focus();
      return;
    }
    setFieldErrors({});
    setSubmitting(true);
    try {
      const updated = await submitMyVerification({
        faculty_code: faculty,
        ticket_number: ticketNumber,
      });
      setTicket('');
      setSuccess(true);
      onSubmitted?.(updated);
    } catch (err) {
      setFormError(verificationErrorMessage(err, 'Не удалось отправить заявку'));
    } finally {
      setSubmitting(false);
    }
  }

  const status = verification?.status ?? 'not_submitted';
  const current = verification?.current ?? null;

  return (
    <section
      id={STUDENT_VERIFICATION_ANCHOR}
      ref={sectionRef}
      tabIndex={-1}
      className={[className, styles.section].filter(Boolean).join(' ')}
      aria-labelledby={headingId}
    >
      <div className={styles.head}>
        <h2 id={headingId} className={styles.title}>Подтверждение студента ДонГУ</h2>
        {!loading && !error && (
          <Badge tone={verificationStatusTone(status)}>{verificationStatusLabel(status)}</Badge>
        )}
      </div>
      <p className={styles.lead}>
        Вы можете подтвердить, что являетесь студентом Донецкого государственного
        университета. Подтверждение не влияет на доступ к тестам и консультациям.
      </p>

      {loading ? (
        <div className={styles.muted}>Загрузка статуса…</div>
      ) : error ? (
        <div className={styles.error} role="alert">{error}</div>
      ) : (
        <>
          {current && (
            <dl className={styles.details}>
              <div className={styles.detailRow}>
                <dt>Факультет</dt>
                <dd>{current.faculty?.label || '—'}</dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Заявка подана</dt>
                <dd>{formatVerificationDate(current.submitted_at)}</dd>
              </div>
              {current.reviewed_at && (
                <div className={styles.detailRow}>
                  <dt>Решение принято</dt>
                  <dd>{formatVerificationDate(current.reviewed_at)}</dd>
                </div>
              )}
            </dl>
          )}

          {status === 'pending' && (
            <p className={styles.note}>
              Заявка на проверке. Изменить её нельзя - дождитесь решения.
            </p>
          )}
          {status === 'approved' && (
            <p className={styles.note}>Ваш статус студента ДонГУ подтверждён.</p>
          )}
          {status === 'rejected' && current?.rejection_reason && (
            <div className={styles.reason}>
              <div className={styles.reasonLabel}>Пояснение</div>
              <p className={styles.reasonText}>{current.rejection_reason}</p>
            </div>
          )}

          {success && (
            <div className={styles.success} role="status">Заявка отправлена на проверку.</div>
          )}

          {canSubmit && (
            <form onSubmit={handleSubmit} className={styles.form} noValidate>
              {status === 'rejected' && (
                <p className={styles.note}>Исправьте данные и отправьте заявку повторно.</p>
              )}
              <Select
                id={facultyId}
                appearance="field"
                label="Факультет"
                placeholder={faculties.loading ? 'Загрузка…' : 'Выберите факультет'}
                value={faculty}
                options={faculties.data}
                onChange={(value) => {
                  setFaculty(value);
                  setFormError('');
                  setFieldErrors((errs) => ({ ...errs, faculty: undefined }));
                }}
                disabled={submitting || faculties.loading}
                error={fieldErrors.faculty || faculties.error || undefined}
              />
              <TextField
                ref={ticketRef}
                id={ticketId}
                appearance="field"
                label="Номер студенческого билета"
                value={ticket}
                onChange={(e) => {
                  setTicket(e.target.value);
                  setFormError('');
                  setFieldErrors((errs) => ({ ...errs, ticket: undefined }));
                }}
                maxLength={TICKET_MAX_LEN}
                autoComplete="off"
                spellCheck={false}
                disabled={submitting}
                error={fieldErrors.ticket}
              />
              {formError && <div className={styles.error} role="alert">{formError}</div>}
              <div className={styles.actions}>
                <Button type="submit" variant="primary" loading={submitting}>
                  Отправить на проверку
                </Button>
              </div>
            </form>
          )}
        </>
      )}
    </section>
  );
}
