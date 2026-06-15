import styles from './FilterChip.module.css';

export default function FilterChip({
  active = false,
  onClick,
  children,
  icon,
  size = 'sm',
  disabled = false,
}) {
  const cls = [
    styles.chip,
    active    && styles.active,
    size === 'md' && styles.md,
    disabled  && styles.disabled,
  ].filter(Boolean).join(' ');

  return (
    <button
      type="button"
      className={cls}
      aria-pressed={active}
      onClick={onClick}
      disabled={disabled}
    >
      {icon}
      {children}
    </button>
  );
}
