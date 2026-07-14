/**
 * A11yToggle — кнопка «Версия для слабовидящих» / «Обычная версия».
 * Доступна на каждой странице: в Navbar и в topbar кабинета.
 * Вне A11yProvider рендерится null (безопасно для изолированных тестов).
 */

import { useContext } from 'react';
import { A11yContext } from './A11yContext';
import styles from './A11yToggle.module.css';

const EyeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path
      d="M1.5 10S4.5 4.5 10 4.5 18.5 10 18.5 10 15.5 15.5 10 15.5 1.5 10 1.5 10z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    <circle cx="10" cy="10" r="2.6" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

/**
 * compact — только иконка (шапка кабинета/админки, где нет места на подпись).
 * Доступное имя даёт aria-label, состояние — aria-pressed.
 */
export default function A11yToggle({ className, compact = false }) {
  const ctx = useContext(A11yContext);
  if (!ctx) return null;

  const { settings, enable, disable } = ctx;
  const on = settings.enabled;
  const label = on ? 'Обычная версия сайта' : 'Версия для слабовидящих';

  return (
    <button
      type="button"
      className={[compact ? styles.iconBtn : styles.btn, on && styles.on, className]
        .filter(Boolean)
        .join(' ')}
      aria-pressed={on}
      aria-label={label}
      title={label}
      onClick={on ? disable : enable}
    >
      <EyeIcon />
      {!compact && (
        <span className={styles.label}>
          {on ? 'Обычная версия' : 'Версия для слабовидящих'}
        </span>
      )}
    </button>
  );
}
