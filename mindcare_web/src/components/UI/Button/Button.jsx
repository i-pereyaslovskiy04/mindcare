import styles from './Button.module.css';

export default function Button({
  variant = 'primary',
  size = 'md',
  tone = 'default',
  type = 'button',
  disabled = false,
  loading = false,
  onClick,
  className,
  children,
  ...props
}) {
  const cls = [
    styles.btn,
    styles[variant] || styles.primary,
    variant !== 'icon' ? styles[size] : (size === 'sm' ? styles.iconSm : ''),
    variant === 'icon' && tone === 'danger' ? styles.iconDanger : '',
    className,
  ].filter(Boolean).join(' ');

  return (
    <button
      type={type}
      className={cls}
      disabled={disabled || loading}
      onClick={onClick}
      {...props}
    >
      {children}
    </button>
  );
}
