/**
 * ThemeToggle — компактный сегментированный переключатель режима темы
 * (Светлая / Тёмная / Системная) для Navbar и topbar кабинета.
 *
 * Feature-specific контрол (обоснование): shared Select — форменный dropdown
 * с порталом и рамкой, избыточен для трёх режимов в шапке; shared Toggle —
 * только boolean. Иконки — inline SVG на currentColor.
 * Вне ThemeProvider рендерится null (безопасно для изолированных тестов).
 */

import { useContext } from 'react';
import { ThemeContext } from './ThemeContext';
import styles from './ThemeToggle.module.css';

const SunIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <circle cx="8" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.4" />
    <path
      d="M8 1.2v1.8M8 13v1.8M1.2 8H3M13 8h1.8M3.2 3.2l1.3 1.3M11.5 11.5l1.3 1.3M12.8 3.2l-1.3 1.3M4.5 11.5l-1.3 1.3"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
    />
  </svg>
);

const MoonIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path
      d="M13.5 9.8A6 6 0 0 1 6.2 2.5a6 6 0 1 0 7.3 7.3z"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinejoin="round"
    />
  </svg>
);

const SystemIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <rect x="1.7" y="2.7" width="12.6" height="8.6" rx="1.3" stroke="currentColor" strokeWidth="1.4" />
    <path d="M5.5 14h5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

const MODE_OPTIONS = [
  { value: 'light', label: 'Светлая тема', Icon: SunIcon },
  { value: 'dark', label: 'Тёмная тема', Icon: MoonIcon },
  { value: 'system', label: 'Системная тема (как в настройках устройства)', Icon: SystemIcon },
];

const PALETTE_OPTIONS = [
  { value: 'coffee', short: 'Кофе', label: 'Кофейная палитра' },
  { value: 'nature', short: 'Природа', label: 'Палитра «Природное спокойствие»' },
  { value: 'classic', short: 'Классика', label: 'Классическая (академическая) палитра' },
  { value: 'hc', short: 'Контраст', label: 'Высококонтрастная тема (для слабовидящих)' },
];

/**
 * withPalette — показывать ли выбор палитры (по умолчанию да);
 * в тесных местах можно отключить и оставить только режим.
 */
export default function ThemeToggle({ className, withPalette = true }) {
  const ctx = useContext(ThemeContext);
  if (!ctx) return null;

  const { mode, setMode, resolvedMode, palette, setPalette } = ctx;

  return (
    <div className={[styles.wrap, className].filter(Boolean).join(' ')}>
      <div className={styles.group} role="group" aria-label="Режим темы оформления">
        {MODE_OPTIONS.map(({ value, label, Icon }) => {
          const isActive = mode === value;
          const title =
            value === 'system'
              ? `${label} — сейчас: ${resolvedMode === 'dark' ? 'тёмная' : 'светлая'}`
              : label;
          return (
            <button
              key={value}
              type="button"
              className={`${styles.option} ${isActive ? styles.optionActive : ''}`}
              aria-pressed={isActive}
              aria-label={title}
              title={title}
              onClick={() => setMode(value)}
            >
              <Icon />
            </button>
          );
        })}
      </div>
      {withPalette && (
        <div className={styles.group} role="group" aria-label="Цветовая палитра">
          {PALETTE_OPTIONS.map(({ value, short, label }) => {
            const isActive = palette === value;
            return (
              <button
                key={value}
                type="button"
                className={`${styles.option} ${styles.optionText} ${
                  isActive ? styles.optionActive : ''
                }`}
                aria-pressed={isActive}
                aria-label={label}
                title={label}
                onClick={() => setPalette(value)}
              >
                {short}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
