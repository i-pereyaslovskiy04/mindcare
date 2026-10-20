import { useEffect, useId, useState } from 'react';
import Modal from '../../../../components/Modal/Modal';
import Button from '../../../../components/UI/Button/Button';
import { deactivateUser, restoreUser } from '../../../../api/users.api';
import styles from './UserLifecycleDialog.module.css';

// Совпадает с backend DEACTIVATION_REASON_MAX_LEN (app/users/schemas.py).
export const DEACTIVATION_REASON_MAX_LEN = 500;

/**
 * Отключение / восстановление аккаунта (ADR-028).
 *
 * mode="deactivate" — обязательная причина (trim, ≤ 500). Аккаунт, email и
 * данные сохраняются, все сессии завершаются; вернуть доступ может только
 * администратор. Причина хранится зашифрованной и нигде не отображается.
 * mode="restore" — подтверждение восстановления (в т.ч. ранее удалённого).
 *
 * Backend авторитетно проверяет причину и запрет отключения себя; здесь —
 * только UX-валидация.
 */
export default function UserLifecycleDialog({ open, mode, userInfo, onClose, onDone }) {
  const [reason, setReason]       = useState('');
  const [reasonError, setReasonError] = useState('');
  const [error, setError]         = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const reasonId = useId();
  const hintId = useId();

  useEffect(() => {
    if (open) {
      setReason('');
      setReasonError('');
      setError(null);
    }
  }, [open, mode, userInfo?.uuid]);

  const isDeactivate = mode === 'deactivate';

  function handleClose() {
    if (submitting) return;
    onClose();
  }

  function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    let request;
    if (isDeactivate) {
      const trimmed = reason.trim();
      if (!trimmed) {
        setReasonError('Укажите причину отключения');
        return;
      }
      if (trimmed.length > DEACTIVATION_REASON_MAX_LEN) {
        setReasonError(`Не более ${DEACTIVATION_REASON_MAX_LEN} символов`);
        return;
      }
      request = deactivateUser(userInfo.uuid, trimmed);
    } else {
      request = restoreUser(userInfo.uuid);
    }
    setSubmitting(true);
    request
      .then(() => { onDone(); })
      .catch((err) => { setError(err.message); })
      .finally(() => { setSubmitting(false); });
  }

  const title = isDeactivate ? 'Отключить аккаунт' : 'Восстановить аккаунт';

  return (
    <Modal open={open} onClose={handleClose} ariaLabel={title} zIndex={2200}>
      <form className={styles.body} onSubmit={handleSubmit} noValidate>
        <h2 className={styles.title}>{title}</h2>

        {isDeactivate ? (
          <>
            <p className={styles.text}>
              Доступ пользователя <strong>{userInfo?.full_name}</strong> будет
              прекращён, все активные сессии завершатся. Аккаунт, email и все
              связанные данные сохранятся. Восстановить доступ может только
              администратор.
            </p>
            <div className={styles.field}>
              <label className={styles.label} htmlFor={reasonId}>
                Причина отключения
              </label>
              <textarea
                id={reasonId}
                className={`${styles.textarea} ${reasonError ? styles.textareaError : ''}`}
                value={reason}
                onChange={(e) => { setReason(e.target.value); setReasonError(''); }}
                maxLength={DEACTIVATION_REASON_MAX_LEN}
                rows={4}
                required
                aria-required="true"
                aria-invalid={reasonError ? 'true' : 'false'}
                aria-describedby={hintId}
                disabled={submitting}
              />
              <div id={hintId} className={styles.hintRow}>
                {reasonError ? (
                  <span className={styles.fieldError} role="alert">{reasonError}</span>
                ) : (
                  <span className={styles.hint}>
                    Причина хранится в защищённом виде и не попадает в журналы.
                  </span>
                )}
                <span className={styles.counter} aria-hidden="true">
                  {reason.length}/{DEACTIVATION_REASON_MAX_LEN}
                </span>
              </div>
            </div>
          </>
        ) : (
          <p className={styles.text}>
            Аккаунт <strong>{userInfo?.full_name}</strong> снова станет активным
            с прежними ролями и данными. Пользователь войдёт заново — прежние
            сессии не восстанавливаются.
          </p>
        )}

        {error && <p className={styles.error} role="alert">{error}</p>}

        <div className={styles.actions}>
          <Button type="button" variant="secondary" onClick={handleClose} disabled={submitting}>
            Отмена
          </Button>
          <Button
            type="submit"
            variant={isDeactivate ? 'danger' : 'primary'}
            loading={submitting}
          >
            {isDeactivate ? 'Отключить аккаунт' : 'Восстановить'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
