import { useState } from 'react';
import Modal from '../../../../components/Modal/Modal';
import { deleteUser } from '../../../../api/users.api';

const S = {
  body:      { padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: '16px' },
  title:     { margin: 0, fontSize: '17px', fontWeight: 600, color: 'var(--espresso)' },
  text:      { margin: 0, fontSize: '13.5px', color: 'var(--text-main)', lineHeight: 1.5 },
  error:     { margin: 0, fontSize: '13px', color: 'var(--error)' },
  actions:   { display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' },
  btnCancel: { height: '40px', padding: '0 18px', border: '1px solid #ddd', borderRadius: '8px', background: 'transparent', fontSize: '14px', fontFamily: 'inherit', cursor: 'pointer' },
  btnDelete: { height: '40px', padding: '0 22px', border: 'none', borderRadius: '8px', background: '#c0392b', color: '#fff', fontSize: '14px', fontFamily: 'inherit', cursor: 'pointer' },
  disabled:  { opacity: 0.55, cursor: 'not-allowed' },
};

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
      .then(()    => { onDeleted(); onClose(); })
      .catch((err) => { setError(err.message); })
      .finally(()  => { setDeleting(false); });
  }

  return (
    <Modal open={open} onClose={handleClose} ariaLabel="Подтверждение удаления" zIndex={2200}>
      <div style={S.body}>
        <h2 style={S.title}>Удалить пользователя</h2>

        <p style={S.text}>
          Вы уверены? Аккаунт <strong>{userInfo?.full_name}</strong> будет деактивирован.
          Все активные сессии будут завершены.
        </p>

        {error && <p style={S.error} role="alert">{error}</p>}

        <div style={S.actions}>
          <button
            type="button"
            style={deleting ? { ...S.btnCancel, ...S.disabled } : S.btnCancel}
            onClick={handleClose}
            disabled={deleting}
          >
            Отмена
          </button>
          <button
            type="button"
            style={deleting ? { ...S.btnDelete, ...S.disabled } : S.btnDelete}
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
