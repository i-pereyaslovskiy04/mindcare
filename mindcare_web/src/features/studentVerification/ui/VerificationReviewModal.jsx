import { useEffect, useId, useState } from 'react';
import Modal from '../../../components/Modal/Modal';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import {
  approveStudentVerification,
  rejectStudentVerification,
} from '../../../api/studentVerification.api';
import useStudentVerificationCard from '../hooks/useStudentVerificationCard';
import {
  VERIFICATION_ERROR_MESSAGES,
  formatVerificationDate,
  formatVerificationDateTime,
  verificationErrorMessage,
  verificationStatusLabel,
  verificationStatusTone,
} from '../lib/status';
import styles from './VerificationReviewModal.module.css';

const REASON_MAX_LEN = 1000;

/**
 * Карточка заявки и решение supervisor'а (ADR-029).
 *
 * Карточка содержит ПОЛНЫЙ номер билета: backend отдаёт его только под аудитом
 * чтения (при сбое аудита — 503 без номера). Кнопки решения — только при
 * `can_review` (pending и заявка не своя); отказ требует пояснения.
 * Номер и пояснение не логируются.
 */
export default function VerificationReviewModal({ uuid, onClose, onDecided }) {
  const open = Boolean(uuid);
  const { data, loading, error } = useStudentVerificationCard(uuid);
  const reasonId = useId();

  const [mode, setMode] = useState('view');      // view | reject
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  useEffect(() => {
    setMode('view');
    setReason('');
    setActionError('');
  }, [uuid]);

  async function decide(action) {
    setActionError('');
    if (action === 'reject' && !reason.trim()) {
      setActionError('Укажите пояснение отказа');
      return;
    }
    setBusy(true);
    try {
      if (action === 'approve') {
        await approveStudentVerification(uuid);
      } else {
        await rejectStudentVerification(uuid, reason.trim());
      }
      onDecided?.();
    } catch (err) {
      setActionError(verificationErrorMessage(err, 'Не удалось сохранить решение'));
    } finally {
      setBusy(false);
    }
  }

  function close() {
    if (!busy) onClose();
  }

  const ownPending = data && data.status === 'pending' && !data.can_review;

  return (
    <Modal open={open} onClose={close} ariaLabel="Заявка на подтверждение студента" size="md">
      <div className={styles.body}>
        <h2 className={styles.title}>Заявка на подтверждение студента ДонГУ</h2>

        {loading && <div className={styles.muted}>Загрузка заявки…</div>}
        {!loading && error && (
          <div className={styles.error} role="alert">
            {verificationErrorMessage(error, 'Не удалось загрузить заявку')}
          </div>
        )}

        {!loading && data && (
          <>
            <dl className={styles.details}>
              <div className={styles.row}>
                <dt>Пользователь</dt>
                <dd>
                  <div className={styles.strong}>{data.student?.full_name}</div>
                  <div className={styles.muted}>{data.student?.email}</div>
                  {data.student?.is_active === false && (
                    <Badge tone="error">Аккаунт отключён</Badge>
                  )}
                </dd>
              </div>
              <div className={styles.row}>
                <dt>Факультет</dt>
                <dd>{data.faculty?.label || '—'}</dd>
              </div>
              <div className={styles.row}>
                <dt>Номер студенческого билета</dt>
                <dd className={styles.ticket}>{data.ticket_number}</dd>
              </div>
              <div className={styles.row}>
                <dt>Подана</dt>
                <dd>{formatVerificationDateTime(data.submitted_at)}</dd>
              </div>
              <div className={styles.row}>
                <dt>Статус</dt>
                <dd>
                  <Badge tone={verificationStatusTone(data.status)}>
                    {verificationStatusLabel(data.status)}
                  </Badge>
                </dd>
              </div>
              {data.reviewed_at && (
                <div className={styles.row}>
                  <dt>Решение</dt>
                  <dd>
                    {formatVerificationDateTime(data.reviewed_at)}
                    {data.reviewer?.full_name ? ` · ${data.reviewer.full_name}` : ''}
                  </dd>
                </div>
              )}
              {data.rejection_reason && (
                <div className={styles.row}>
                  <dt>Пояснение отказа</dt>
                  <dd className={styles.reason}>{data.rejection_reason}</dd>
                </div>
              )}
            </dl>

            {data.history?.length > 0 && (
              <div className={styles.history}>
                <div className={styles.historyTitle}>Предыдущие заявки</div>
                <ul className={styles.historyList}>
                  {data.history.map((h) => (
                    <li key={h.uuid} className={styles.historyItem}>
                      <Badge tone={verificationStatusTone(h.status)}>
                        {verificationStatusLabel(h.status)}
                      </Badge>
                      <span>{h.faculty?.label || '—'}</span>
                      <span className={styles.muted}>
                        {formatVerificationDate(h.submitted_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {ownPending && (
              <p className={styles.note}>{VERIFICATION_ERROR_MESSAGES.self_review_forbidden}</p>
            )}

            {mode === 'reject' && (
              <div className={styles.field}>
                <label htmlFor={reasonId} className={styles.label}>
                  Пояснение отказа (увидит пользователь)
                </label>
                <textarea
                  id={reasonId}
                  className={styles.textarea}
                  value={reason}
                  onChange={(e) => { setReason(e.target.value); setActionError(''); }}
                  maxLength={REASON_MAX_LEN}
                  rows={4}
                  disabled={busy}
                />
              </div>
            )}

            {actionError && <div className={styles.error} role="alert">{actionError}</div>}
          </>
        )}

        <div className={styles.actions}>
          {data?.can_review && mode === 'view' && (
            <>
              <Button type="button" variant="danger" onClick={() => setMode('reject')} disabled={busy}>
                Отклонить
              </Button>
              <Button type="button" variant="primary" onClick={() => decide('approve')} loading={busy}>
                Подтвердить
              </Button>
            </>
          )}
          {data?.can_review && mode === 'reject' && (
            <>
              <Button type="button" variant="secondary" onClick={() => setMode('view')} disabled={busy}>
                Назад
              </Button>
              <Button type="button" variant="danger" onClick={() => decide('reject')} loading={busy}>
                Отклонить заявку
              </Button>
            </>
          )}
          {!(data?.can_review) && (
            <Button type="button" variant="secondary" onClick={close}>Закрыть</Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
