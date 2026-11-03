import Modal from '../../../components/Modal/Modal';
import Button from '../../../components/UI/Button/Button';
import styles from './ConfirmDialog.module.css';

/**
 * Подтверждение необратимого действия с заданием (выполнение / отмена).
 * Оформление — как у остальных диалогов кабинетов на общем Modal
 * (UserLifecycleDialog): заголовок, пояснение, блок ошибки, «Отмена» +
 * основное действие; на узком экране кнопки в столбик.
 * Пока запрос идёт, кнопки заблокированы (защита от двойной отправки).
 */
export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  confirmTone = 'primary',
  loading = false,
  error = null,
  onConfirm,
  onClose,
}) {
  return (
    <Modal open={open} onClose={loading ? () => {} : onClose} ariaLabel={title} zIndex={2200}>
      <div className={styles.body}>
        <h2 className={styles.title}>{title}</h2>
        {description && <p className={styles.text}>{description}</p>}
        {error && <p className={styles.error} role="alert">{error}</p>}
        <div className={styles.actions}>
          <Button type="button" variant="secondary" onClick={onClose} disabled={loading}>
            Отмена
          </Button>
          <Button
            type="button"
            variant={confirmTone === 'danger' ? 'danger' : 'primary'}
            onClick={onConfirm}
            loading={loading}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
