import { useState } from 'react';
import Modal from '../../../../components/Modal/Modal';
import { deleteUser } from '../../../../api/users.api';
import styles from './DeleteConfirmDialog.module.css';

export default function DeleteConfirmDialog({ open, userInfo, onClose, onDeleted }) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError]       = useState(null);

  function handleClose() {
    setError(null);
    onClose();
  }

  function handleDelete() {
    setDeleting(true);
    deleteUser(userInfo.uuid)
      .then(()     => { onDeleted(); onClose(); })
      .catch((err) => { setError(err.message); })
      .finally(()  => { setDeleting(false); });
  }

  return (
    <Modal open={open} onClose={handleClose} ariaLabel="Подтверждение удаления" zIndex={2200}>
      <div className={styles.body}>
        <h2 className={styles.title}>Удалить пользователя</h2>

        <p className={styles.text}>
          Вы уверены? Аккаунт <strong>{userInfo?.full_name}</strong> будет деактивирован.
          Все активные сессии будут завершены.
        </p>

        {error && <p className={styles.error} role="alert">{error}</p>}

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.btnCancel}
            onClick={handleClose}
            disabled={deleting}
          >
            Отмена
          </button>
          <button
            type="button"
            className={styles.btnDelete}
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting ? 'Удаляем…' : 'Удалить'}
          </button>
        </div>
      </div>
    </Modal>
  );
}
