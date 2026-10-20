/**
 * ThemePreviewPage — dev-only демо всех тем (/theme-preview).
 *
 * Ключевые компоненты и токен-пары во всех темах; переключение — обычным
 * ThemeToggle. Роут подключается только вне production (см. router.jsx).
 */

import Button from '../../components/UI/Button/Button';
import Badge from '../../components/UI/Badge/Badge';
import ThemeToggle from '../../features/theme/ThemeToggle';
import { useTheme } from '../../features/theme/ThemeContext';
import styles from './ThemePreviewPage.module.css';

const TOKEN_PAIRS = [
  ['--text-main', '--warm-white', 'Основной текст'],
  ['--text-muted', '--cream', 'Второстепенный текст'],
  ['--milk', '--espresso', 'Button.primary'],
  ['--on-primary', '--primary', 'Акцент (primary)'],
  ['--on-secondary', '--secondary', 'Secondary'],
  ['--error', '--error-bg', 'Ошибка'],
  ['--success', '--success-bg', 'Успех'],
  ['--warning-text', '--warning-bg', 'Предупреждение'],
  ['--info-text', '--info-bg', 'Info'],
  ['--tag-text', '--tag-bg', 'Тег'],
  ['--code-text', '--code-bg', 'Код'],
];

export default function ThemePreviewPage() {
  const { resolvedTheme } = useTheme();

  return (
    <div className={styles.page}>
      <div className="container">
        <header className={styles.header}>
          <h1>Theme preview</h1>
          <p className={styles.sub}>
            Текущая тема: <code>{resolvedTheme}</code>
          </p>
          <ThemeToggle />
        </header>

        <section className={styles.section}>
          <h2>Кнопки</h2>
          <div className={styles.row}>
            <Button>Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="danger">Danger</Button>
            <Button variant="ghost">Ghost</Button>
            <Button disabled>Disabled</Button>
          </div>
        </section>

        <section className={styles.section}>
          <h2>Бейджи</h2>
          <div className={styles.row}>
            <Badge tone="success">Опубликовано</Badge>
            <Badge tone="warning">Черновик</Badge>
            <Badge tone="error">Заблокирован</Badge>
            <Badge tone="neutral">Нейтральный</Badge>
          </div>
        </section>

        <section className={styles.section}>
          <h2>Карточки и поверхности</h2>
          <div className={styles.cards}>
            <div className={styles.card}>
              <h3>Обычная карточка</h3>
              <p className={styles.mutedText}>Второстепенный текст на warm-white.</p>
              <p className={styles.lightText}>Приглушённая подпись (text-light).</p>
            </div>
            <div className={styles.darkCard}>
              <h3>Тёмная карточка</h3>
              <p>Текст text-on-dark на espresso.</p>
            </div>
            <div className={styles.altCard}>
              <h3>Alt-фон (cream)</h3>
              <p className={styles.mutedText}>Границы — nav-border, тень — shadow-md.</p>
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <h2>Форма</h2>
          <div className={styles.formDemo}>
            <label className={styles.label} htmlFor="preview-input">
              Текстовое поле
              <input id="preview-input" className={styles.input} placeholder="Placeholder…" />
            </label>
            <p className={styles.errorNote} role="presentation">Пример текста ошибки на error-bg</p>
            <p className={styles.successNote} role="presentation">Пример success-сообщения</p>
          </div>
        </section>

        <section className={styles.section}>
          <h2>Токен-пары (текст / фон)</h2>
          <div className={styles.tokens}>
            {TOKEN_PAIRS.map(([fg, bg, label]) => (
              <div
                key={`${fg}-${bg}`}
                className={styles.tokenChip}
                style={{ color: `var(${fg})`, background: `var(${bg})` }}
              >
                {label}
                <span className={styles.tokenNames}>
                  {fg} / {bg}
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
