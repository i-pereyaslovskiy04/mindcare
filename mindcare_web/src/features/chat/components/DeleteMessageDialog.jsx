import Modal from '../../../components/Modal/Modal';
import Button from '../../../components/UI/Button/Button';
import styles from './DeleteMessageDialog.module.css';

/**
 * Подтверждение удаления сообщения (Stage 31y).
 *
 * Использует shared Modal + shared Button. Удаление выполняется только после
 * подтверждения; «Удалить» — danger-вариант кнопки.
 */
export default function DeleteMessageDialog({ open, deleting = false, onConfirm, onCancel }) {
  return (
    <Modal open={open} onClose={onCancel} ariaLabel="Удалить сообщение" zIndex={2300}>
      <div className={styles.body}>
        <h2 className={styles.title}>Удалить сообщение?</h2>
        <p className={styles.text}>
          Сообщение будет удалено у вас и у собеседника и пропадёт из переписки.
          Это действие нельзя отменить.
        </p>
        <div className={styles.actions}>
          <Button variant="secondary" onClick={onCancel} disabled={deleting}>
            Отмена
          </Button>
          <Button variant="danger" onClick={onConfirm} loading={deleting}>
            {deleting ? 'Удаляем…' : 'Удалить'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
