import styles from './Toggle.module.css';

export default function Toggle({
  id,
  checked,
  onChange,
  label,
  disabled = false,
}) {
  return (
    <button
      id={id}
      type="button"
      className={[
        styles.track,
        checked  && styles.checked,
        disabled && styles.disabled,
      ].filter(Boolean).join(' ')}
      aria-pressed={checked}
      aria-label={typeof label === 'string' ? label : undefined}
      disabled={disabled}
      onClick={(e) => onChange?.(!checked, e)}
    >
      <span className={styles.thumb} />
    </button>
  );
}
