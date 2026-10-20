import { Link } from 'react-router-dom';

import styles from './Button.module.css';

export default function ButtonLink({
  to,
  variant = 'primary',
  size = 'md',
  tone = 'default',
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
    <Link to={to} className={cls} {...props}>
      {children}
    </Link>
  );
}
