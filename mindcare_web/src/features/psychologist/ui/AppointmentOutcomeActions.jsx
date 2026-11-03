import { useState } from 'react';
import Button from '../../../components/UI/Button/Button';
import ConfirmDialog from '../../assignments/ui/ConfirmDialog';
import { OUTCOME_LABELS } from '../lib/meetingFormat';
import styles from './AppointmentOutcomeActions.module.css';

const DIALOG = {
  completed: {
    title: 'Отметить встречу как состоявшуюся?',
    confirmLabel: OUTCOME_LABELS.completed,
  },
  no_show: {
    title: 'Отметить неявку клиента?',
    confirmLabel: OUTCOME_LABELS.no_show,
  },
};

/**
 * Кнопки итога прошедшей подтверждённой встречи: «Состоялась» / «Неявка».
 * outcome — экземпляр useAppointmentOutcome (один на список: одна отправка за
 * раз). Итог окончательный, поэтому перед отправкой — подтверждение.
 */
export default function AppointmentOutcomeActions({ appointment, outcome }) {
  const [choice, setChoice] = useState(null);
  const busy = outcome.pending?.uuid === appointment.uuid;
  const error = outcome.error?.uuid === appointment.uuid ? outcome.error.message : null;
  const errorId = `outcome-error-${appointment.uuid}`;

  async function submit() {
    if (!choice) return;
    await outcome.mark(appointment.uuid, choice);
    setChoice(null);
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.buttons} role="group" aria-label="Итог встречи">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={Boolean(outcome.pending)}
          aria-describedby={error ? errorId : undefined}
          onClick={() => setChoice('completed')}
        >
          {OUTCOME_LABELS.completed}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={Boolean(outcome.pending)}
          aria-describedby={error ? errorId : undefined}
          onClick={() => setChoice('no_show')}
        >
          {OUTCOME_LABELS.no_show}
        </Button>
      </div>
      {error && <p id={errorId} className={styles.error} role="alert">{error}</p>}
      <ConfirmDialog
        open={choice !== null}
        title={choice ? DIALOG[choice].title : ''}
        description="Итог сохраняется окончательно: изменить его будет нельзя."
        confirmLabel={choice ? DIALOG[choice].confirmLabel : ''}
        loading={busy}
        onConfirm={submit}
        onClose={() => setChoice(null)}
      />
    </div>
  );
}
