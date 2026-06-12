import { useState } from 'react';
import Modal from '../../../../components/Modal/Modal';
import { useUserForm } from '../hooks/useUserForm';
import Select from '../../../../components/UI/Select/Select';
import Button from '../../../../components/UI/Button/Button';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import styles from './UserCreateModal.module.css';

const ROLE_OPTIONS = [
  { value: 'supervisor',   label: 'Супервизор' },
  { value: 'psychologist', label: 'Психолог' },
  { value: 'admin',        label: 'Администратор' },
];

const BASIS_TYPE_OPTIONS = [
  { value: 'service_duty',         label: 'Служебная необходимость' },
  { value: 'employment',           label: 'Трудовое основание' },
  { value: 'contract',             label: 'Договор' },
  { value: 'administrative_order', label: 'Административный приказ' },
  { value: 'other',                label: 'Иное' },
];

const LEGAL_BASIS_LABEL =
  'Подтверждаю наличие документированного основания для создания ' +
  'учётной записи и обработки персональных данных пользователя.';

export default function UserCreateModal({ open, onClose, onCreated }) {
  const [createdUser, setCreatedUser] = useState(null);

  const { values, errors, submitting, handleChange, handleSubmit, reset } = useUserForm({
    mode: 'create',
    onSuccess: (result) => setCreatedUser(result),
  });

  function handleClose() {
    if (createdUser) onCreated();
    setCreatedUser(null);
    reset();
    onClose();
  }

  return (
    <Modal open={open} onClose={handleClose} ariaLabel="Создать пользователя" zIndex={2200}>
      {createdUser ? (
        <SuccessScreen user={createdUser} onClose={handleClose} />
      ) : (
        <CreateForm
          values={values}
          errors={errors}
          submitting={submitting}
          onChange={handleChange}
          onSubmit={handleSubmit}
          onCancel={handleClose}
        />
      )}
    </Modal>
  );
}

function CreateForm({ values, errors, submitting, onChange, onSubmit, onCancel }) {
  return (
    <div className={styles.body}>
      <h2 className={styles.title}>Новый пользователь</h2>

      <form onSubmit={onSubmit} noValidate>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="ucm-full_name">ФИО</label>
          <input
            id="ucm-full_name"
            className={`${styles.input} ${errors.full_name ? styles.inputError : ''}`}
            type="text"
            name="full_name"
            value={values.full_name}
            onChange={onChange}
            placeholder="Иванова Мария Сергеевна"
            autoComplete="off"
          />
          {errors.full_name && (
            <span className={styles.hint} role="alert">{errors.full_name}</span>
          )}
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="ucm-email">Email</label>
          <input
            id="ucm-email"
            className={`${styles.input} ${errors.email ? styles.inputError : ''}`}
            type="email"
            name="email"
            value={values.email}
            onChange={onChange}
            placeholder="ivanova@donstu.ru"
            autoComplete="off"
          />
          {errors.email && (
            <span className={styles.hint} role="alert">{errors.email}</span>
          )}
        </div>

        <div className={styles.field}>
          <label className={styles.label}>Роль</label>
          <Select
            value={values.role}
            options={ROLE_OPTIONS}
            onChange={(val) => onChange({ target: { name: 'role', value: val } })}
            error={errors.role}
            panelZIndex={2300}
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label}>Тип основания</label>
          <Select
            value={values.basis_type}
            options={BASIS_TYPE_OPTIONS}
            onChange={(val) => onChange({ target: { name: 'basis_type', value: val } })}
            error={errors.basis_type}
            panelZIndex={2300}
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="ucm-basis_reference">
            Документ-основание (необязательно)
          </label>
          <input
            id="ucm-basis_reference"
            className={styles.input}
            type="text"
            name="basis_reference"
            value={values.basis_reference}
            onChange={onChange}
            placeholder="Например: приказ №..., договор №..."
            autoComplete="off"
            maxLength={255}
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="ucm-legal_basis_comment">
            Комментарий (необязательно)
          </label>
          <input
            id="ucm-legal_basis_comment"
            className={styles.input}
            type="text"
            name="legal_basis_comment"
            value={values.legal_basis_comment}
            onChange={onChange}
            autoComplete="off"
          />
        </div>

        <div className={styles.field}>
          <Checkbox
            id="ucm-legal_basis_confirmed"
            checked={values.legal_basis_confirmed}
            error={Boolean(errors.legal_basis_confirmed)}
            ariaDescribedBy={errors.legal_basis_confirmed ? 'ucm-lb-error' : undefined}
            onChange={(checked) =>
              onChange({
                target: { name: 'legal_basis_confirmed', type: 'checkbox', checked },
              })
            }
            label={LEGAL_BASIS_LABEL}
          />
          {errors.legal_basis_confirmed && (
            <span id="ucm-lb-error" className={styles.hint} role="alert">
              {errors.legal_basis_confirmed}
            </span>
          )}
        </div>

        {errors._form && (
          <div className={styles.formError} role="alert">{errors._form}</div>
        )}

        <div className={styles.actions}>
          <Button variant="secondary" onClick={onCancel} disabled={submitting}>
            Отмена
          </Button>
          <Button
            variant="primary"
            type="submit"
            disabled={submitting || !values.legal_basis_confirmed}
          >
            {submitting ? 'Создаём…' : 'Создать'}
          </Button>
        </div>
      </form>
    </div>
  );
}

function SuccessScreen({ user, onClose }) {
  return (
    <div className={styles.body}>
      <div className={styles.successIcon} aria-hidden="true">✓</div>
      <h2 className={styles.title}>Пользователь создан</h2>
      <p className={styles.successName}>{user.full_name}</p>
      <p className={styles.successEmail}>{user.email}</p>

      <div className={styles.passwordBlock}>
        <p className={styles.passwordLabel}>Временный пароль</p>
        <p className={styles.password}>{user.temporary_password}</p>
        <p className={styles.passwordNote}>Пароль также отправлен на почту пользователя</p>
      </div>

      <div className={styles.actions}>
        <Button variant="primary" onClick={onClose}>
          Закрыть
        </Button>
      </div>
    </div>
  );
}
