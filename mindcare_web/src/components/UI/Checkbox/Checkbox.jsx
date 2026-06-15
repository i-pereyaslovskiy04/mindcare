import styles from './Checkbox.module.css';

export default function Checkbox({
  id,
  checked,
  onChange,
  label,
  disabled = false,
  error = false,
  ariaDescribedBy,
  className,
}) {
  return (
    <label
      className={[
        styles.label,
        error    && styles.labelError,
        disabled && styles.disabled,
        className,
      ].filter(Boolean).join(' ')}
    >
      <input
        id={id}
        type="checkbox"
        className={styles.input}
        checked={checked}
        disabled={disabled}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={ariaDescribedBy}
        onChange={(e) => onChange?.(e.target.checked, e)}
      />
      {label != null && <span className={styles.text}>{label}</span>}
    </label>
  );
}
