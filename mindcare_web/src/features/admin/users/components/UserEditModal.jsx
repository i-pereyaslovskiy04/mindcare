import Modal from '../../../../components/Modal/Modal';
import { useUserForm } from '../hooks/useUserForm';
import Select from '../../../../components/UI/Select/Select';
import Button from '../../../../components/UI/Button/Button';
import styles from './UserEditModal.module.css';

const ROLE_OPTIONS = [
  { value: 'student',      label: 'Студент' },
  { value: 'psychologist', label: 'Психолог' },
  { value: 'admin',        label: 'Администратор' },
  { value: 'supervisor',   label: 'Супервизор' },
];

function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('ru-RU');
}

export default function UserEditModal({ open, uuid, userInfo, onClose, onUpdated }) {
  const { values, errors, loading, submitting, handleChange, handleSubmit } = useUserForm({
    mode: 'edit',
    uuid,
    onSuccess: () => { onUpdated(); onClose(); },
  });

  return (
    <Modal open={open} onClose={onClose} ariaLabel="Редактировать пользователя" zIndex={2200}>
      <div className={styles.body}>
        <h2 className={styles.title}>Редактировать пользователя</h2>

        {loading ? (
          <Skeleton />
        ) : (
          <form onSubmit={handleSubmit} noValidate>
            <div className={styles.roGroup}>
              <div className={styles.roField}>
                <span className={styles.roLabel}>Email</span>
                <input
                  className={`${styles.input} ${styles.inputReadonly}`}
                  type="text"
                  value={userInfo?.email ?? ''}
                  readOnly
                  tabIndex={-1}
                />
              </div>
              <div className={styles.roField}>
                <span className={styles.roLabel}>Дата регистрации</span>
                <span className={styles.roValue}>{formatDate(userInfo?.created_at)}</span>
              </div>
              <div className={styles.roField}>
                <span className={styles.roLabel}>Последний вход</span>
                <span className={styles.roValue}>{formatDate(userInfo?.last_login)}</span>
              </div>
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="uem-full_name">ФИО</label>
              <input
                id="uem-full_name"
                className={`${styles.input} ${errors.full_name ? styles.inputError : ''}`}
                type="text"
                name="full_name"
                value={values.full_name}
                onChange={handleChange}
              />
              {errors.full_name && (
                <span className={styles.hint} role="alert">{errors.full_name}</span>
              )}
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="uem-phone">Телефон</label>
              <input
                id="uem-phone"
                className={styles.input}
                type="text"
                name="phone"
                value={values.phone}
                onChange={handleChange}
                placeholder="+7 (900) 000-00-00"
              />
            </div>

            <div className={styles.field}>
              <label className={styles.label}>Роль</label>
              <Select
                value={values.role}
                options={ROLE_OPTIONS}
                onChange={(val) => handleChange({ target: { name: 'role', value: val } })}
                error={errors.role}
                panelZIndex={2300}
              />
            </div>

            <div className={styles.checkboxField}>
              <label className={styles.checkboxLabel}>
                <input
                  className={styles.checkbox}
                  type="checkbox"
                  name="is_active"
                  checked={values.is_active}
                  onChange={handleChange}
                />
                Активен
              </label>
            </div>

            {errors._form && (
              <div className={styles.formError} role="alert">{errors._form}</div>
            )}

            <div className={styles.actions}>
              <Button variant="secondary" onClick={onClose} disabled={submitting}>
                Отмена
              </Button>
              <Button variant="primary" type="submit" disabled={submitting || loading}>
                {submitting ? 'Сохраняем…' : 'Сохранить'}
              </Button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
}

function Skeleton() {
  return (
    <div className={styles.skeleton} aria-hidden="true">
      <div className={styles.skeletonLine} style={{ width: '40%' }} />
      <div className={styles.skeletonInput} />
      <div className={styles.skeletonLine} style={{ width: '40%' }} />
      <div className={styles.skeletonInput} />
      <div className={styles.skeletonLine} style={{ width: '30%' }} />
      <div className={styles.skeletonInput} />
    </div>
  );
}
