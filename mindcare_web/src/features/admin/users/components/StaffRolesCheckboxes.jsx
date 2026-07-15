import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import Badge from '../../../../components/UI/Badge/Badge';
import { STAFF_ROLE_OPTIONS, ROLE_LABELS, ROLE_BADGE_TONES } from '../roleLabels';
import styles from './StaffRolesCheckboxes.module.css';

/**
 * Multi-role staff-контрол (ADR-018): группа из 3 чекбоксов
 * (admin/supervisor/psychologist). `student` не выбирается через админку —
 * если он уже назначен, показываем его как read-only badge над чекбоксами и
 * НЕ отправляем в payload (backend сохраняет его сам).
 *
 * Props:
 *   value: string[]      — выбранные staff-роли;
 *   onToggle: (role) => void;
 *   hasStudent: boolean  — показать read-only student badge;
 *   disabled?: boolean   — недоступно назначать/снимать staff-роль (backend
 *     разрешает изменение staff-набора только тому, у кого уже есть staff-роль:
 *     roleless/student-only edit-форма показывает disabled-контрол вместо 422);
 *   disabledHint?: string — пояснение, показывается только при disabled;
 *   error?: string;
 *   idPrefix?: string.
 */
export default function StaffRolesCheckboxes({
  value = [],
  onToggle,
  hasStudent = false,
  disabled = false,
  disabledHint,
  error,
  label = 'Роли',
  idPrefix = 'staff-roles',
}) {
  return (
    <div className={styles.wrap}>
      <span className={styles.label}>{label}</span>

      {hasStudent && (
        <div className={styles.studentRow}>
          <Badge tone={ROLE_BADGE_TONES.student}>{ROLE_LABELS.student}</Badge>
          <span className={styles.readonlyNote}>
            назначена при регистрации, не меняется здесь
          </span>
        </div>
      )}

      <div
        className={styles.options}
        role="group"
        aria-label={label}
      >
        {STAFF_ROLE_OPTIONS.map((opt) => (
          <Checkbox
            key={opt.value}
            id={`${idPrefix}-${opt.value}`}
            checked={value.includes(opt.value)}
            onChange={() => onToggle(opt.value)}
            label={opt.label}
            disabled={disabled}
          />
        ))}
      </div>

      {disabled && disabledHint && (
        <span className={styles.readonlyNote}>{disabledHint}</span>
      )}

      {error && (
        <span className={styles.hint} role="alert">{error}</span>
      )}
    </div>
  );
}
