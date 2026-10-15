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
  HISTORY_ACTOR_UNAVAILABLE,
  HISTORY_EVENT_LABELS,
  HISTORY_EVENT_TONES,
  STALE_VERIFICATION_CODES,
  VERIFICATION_ERROR_MESSAGES,
  formatVerificationDateTime,
  verificationErrorMessage,
  verificationStatusLabel,
  verificationStatusTone,
} from '../lib/status';
import styles from './VerificationReviewModal.module.css';

const REASON_MAX_LEN = 1000;

/** Заявки (от новых к старым) → плоская лента событий, тоже от новых к старым. */
function historyEvents(items) {
  return items.flatMap((item) => (item.events || []).map((event, index) => ({
    key: `${item.uuid}:${index}`,
    item,
    event,
  })));
}

function actorLine(event) {
  const isDecision = event.type === 'rejected' || event.type === 'approved';
  if (!event.actor?.full_name) {
    return isDecision ? HISTORY_ACTOR_UNAVAILABLE : 'Заявитель: сведения недоступны';
  }
  return `${isDecision ? 'Проверил(а)' : 'Заявитель'}: ${event.actor.full_name}`;
}

function VerificationHistory({ card }) {
  const {
    history, hasMoreHistory, historyLoading, historyError, loadMoreHistory,
  } = card;
  const events = historyEvents(history);
  if (events.length === 0) return null;
  return (
    <section className={styles.history} aria-label="История подтверждения">
      <h3 className={styles.historyTitle}>История подтверждения</h3>
      <ol className={styles.timeline}>
        {events.map(({ key, item, event }) => (
          <li key={key} className={styles.event}>
            <div className={styles.eventHead}>
              <Badge tone={HISTORY_EVENT_TONES[event.type] ?? 'neutral'}>
                {HISTORY_EVENT_LABELS[event.type] ?? event.type}
              </Badge>
              <time className={styles.eventTime} dateTime={event.at}>
                {formatVerificationDateTime(event.at)}
              </time>
              {item.is_current && (
                <span className={styles.currentMark}>текущая заявка</span>
              )}
            </div>
            <div className={styles.eventMeta}>{actorLine(event)}</div>
            {(event.type === 'submitted' || event.type === 'resubmitted') && (
              <div className={styles.eventMeta}>Факультет: {item.faculty?.label || '—'}</div>
            )}
            {event.type === 'rejected' && event.reason && (
              <div className={styles.eventReason}>
                <span className={styles.eventMeta}>Причина отказа:</span> {event.reason}
              </div>
            )}
          </li>
        ))}
      </ol>
      {historyError && (
        <div className={styles.error} role="alert">
          {verificationErrorMessage(historyError, 'Не удалось загрузить историю')}
        </div>
      )}
      {hasMoreHistory && (
        <div className={styles.historyMore}>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={loadMoreHistory}
            loading={historyLoading}
          >
            Показать ещё
          </Button>
        </div>
      )}
    </section>
  );
}

/**
 * Карточка заявки и решение supervisor'а (ADR-029).
 *
 * Карточка содержит ПОЛНЫЙ номер билета и историю подтверждения пользователя
 * с причинами прежних отказов: backend отдаёт их только под аудитом чтения
 * (при сбое аудита — 503 без номера и причин). Кнопки решения — только при
 * `can_review` (pending и заявка не своя); отказ требует пояснения. Если
 * заявку уже решил другой супервизор (409/404), кнопки скрываются, а очередь
 * и счётчик обновляются (onStale). Номер и пояснения не логируются.
 */
export default function VerificationReviewModal({ uuid, onClose, onDecided, onStale }) {
  const open = Boolean(uuid);
  const card = useStudentVerificationCard(uuid);
  const { data, loading, error } = card;
  const reasonId = useId();

  const [mode, setMode] = useState('view');      // view | reject
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [stale, setStale] = useState(false);

  useEffect(() => {
    setMode('view');
    setReason('');
    setActionError('');
    setStale(false);
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
      if (STALE_VERIFICATION_CODES.includes(err?.code)) {
        setStale(true);
        setMode('view');
        onStale?.();
      }
    } finally {
      setBusy(false);
    }
  }

  function close() {
    if (!busy) onClose();
  }

  const canReview = Boolean(data?.can_review) && !stale;
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

            <VerificationHistory card={card} />

            {ownPending && (
              <p className={styles.note}>{VERIFICATION_ERROR_MESSAGES.self_review_forbidden}</p>
            )}

            {mode === 'reject' && canReview && (
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
          {canReview && mode === 'view' && (
            <>
              <Button type="button" variant="danger" onClick={() => setMode('reject')} disabled={busy}>
                Отклонить
              </Button>
              <Button type="button" variant="primary" onClick={() => decide('approve')} loading={busy}>
                Подтвердить
              </Button>
            </>
          )}
          {canReview && mode === 'reject' && (
            <>
              <Button type="button" variant="secondary" onClick={() => setMode('view')} disabled={busy}>
                Назад
              </Button>
              <Button type="button" variant="danger" onClick={() => decide('reject')} loading={busy}>
                Отклонить заявку
              </Button>
            </>
          )}
          {!canReview && (
            <Button type="button" variant="secondary" onClick={close}>Закрыть</Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
