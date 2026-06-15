import Modal from '../../../../components/Modal/Modal';
import { useUserForm } from '../hooks/useUserForm';
import Button from '../../../../components/UI/Button/Button';
import Select from '../../../../components/UI/Select/Select';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import { EDIT_ROLE_OPTIONS, ROLE_LABELS, isStaffRole } from '../roleLabels';
import { BASIS_TYPE_OPTIONS, ROLE_CHANGE_LEGAL_BASIS_LABEL } from '../legalBasis';
import { PHONE_PLACEHOLDER } from '../phone';
import styles from './UserEditModal.module.css';

function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('ru-RU');
}

export default function UserEditModal({ open, uuid, userInfo, onClose, onUpdated }) {
  const { values, errors, loading, submitting, handleChange, handleSubmit, initialRole } =
    useUserForm({
      mode: 'edit',
      uuid,
      onSuccess: () => { onUpdated(); onClose(); },
    });

  // Legal basis нужен только при реальной смене роли на staff/admin.
  const roleChanged = initialRole != null && values.role !== initialRole;
  const showLegalBasis = roleChanged && isStaffRole(values.role);

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
              <label className={styles.label}>Роль пользователя</label>
              <Select
                value={values.role}
                options={EDIT_ROLE_OPTIONS}
                displayLabel={ROLE_LABELS[values.role]}
                onChange={(val) => handleChange({ target: { name: 'role', value: val } })}
                error={errors.role}
                panelZIndex={2300}
              />
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
                placeholder={PHONE_PLACEHOLDER}
              />
            </div>

            <div className={styles.checkboxField}>
              <Checkbox
                checked={values.is_active}
                onChange={(val) => handleChange({ target: { name: 'is_active', type: 'checkbox', checked: val } })}
                label="Активен"
              />
            </div>

            {showLegalBasis && (
              <div className={styles.legalBasisGroup}>
                <p className={styles.legalBasisNote}>
                  Смена роли на «{ROLE_LABELS[values.role] ?? values.role}»
                  требует документированного основания обработки ПДн.
                </p>

                <div className={styles.field}>
                  <label className={styles.label}>Тип основания</label>
                  <Select
                    value={values.basis_type}
                    options={BASIS_TYPE_OPTIONS}
                    onChange={(val) => handleChange({ target: { name: 'basis_type', value: val } })}
                    error={errors.basis_type}
                    panelZIndex={2300}
                  />
                </div>

                <div className={styles.field}>
                  <label className={styles.label} htmlFor="uem-basis_reference">
                    Документ-основание
                  </label>
                  <input
                    id="uem-basis_reference"
                    className={`${styles.input} ${errors.basis_reference ? styles.inputError : ''}`}
                    type="text"
                    name="basis_reference"
                    value={values.basis_reference}
                    onChange={handleChange}
                    placeholder="Например: приказ №..., договор №..."
                    autoComplete="off"
                    maxLength={255}
                  />
                  {errors.basis_reference && (
                    <span className={styles.hint} role="alert">{errors.basis_reference}</span>
                  )}
                </div>

                <div className={styles.field}>
                  <label className={styles.label} htmlFor="uem-legal_basis_comment">
                    Комментарий (необязательно)
                  </label>
                  <input
                    id="uem-legal_basis_comment"
                    className={styles.input}
                    type="text"
                    name="legal_basis_comment"
                    value={values.legal_basis_comment}
                    onChange={handleChange}
                    autoComplete="off"
                  />
                </div>

                <div className={styles.checkboxField}>
                  <Checkbox
                    id="uem-legal_basis_confirmed"
                    checked={values.legal_basis_confirmed}
                    error={Boolean(errors.legal_basis_confirmed)}
                    ariaDescribedBy={errors.legal_basis_confirmed ? 'uem-lb-error' : undefined}
                    onChange={(checked) =>
                      handleChange({
                        target: { name: 'legal_basis_confirmed', type: 'checkbox', checked },
                      })
                    }
                    label={ROLE_CHANGE_LEGAL_BASIS_LABEL}
                  />
                  {errors.legal_basis_confirmed && (
                    <span id="uem-lb-error" className={styles.hint} role="alert">
                      {errors.legal_basis_confirmed}
                    </span>
                  )}
                </div>
              </div>
            )}

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
