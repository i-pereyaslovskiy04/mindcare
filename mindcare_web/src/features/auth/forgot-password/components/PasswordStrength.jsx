import styles from '../styles/forgot-password.module.css';

const LEVELS = [
  { barCls: styles.strengthWeak,   labelCls: styles.strengthLabelWeak,   label: 'Слабый' },
  { barCls: styles.strengthMedium, labelCls: styles.strengthLabelMedium, label: 'Средний' },
  { barCls: styles.strengthStrong, labelCls: styles.strengthLabelStrong, label: 'Надёжный' },
];

function calcLevel(v) {
  let s = 0;
  if (v.length >= 8) s++;
  if (/[A-Z]|[А-ЯЁ]/.test(v)) s++;
  if (/[0-9]/.test(v)) s++;
  if (/[^a-zA-Zа-яёА-ЯЁ0-9]/.test(v)) s++;
  return s <= 1 ? 0 : s <= 2 ? 1 : 2;
}

export default function PasswordStrength({ value }) {
  const lvl = value ? calcLevel(value) : null;
  const meta = lvl !== null ? LEVELS[lvl] : null;

  return (
    <div className={styles.strength}>
      <div className={styles.strengthBars}>
        {[0, 1, 2].map(i => (
          <div
            key={i}
            className={`${styles.strengthBar} ${meta && i <= lvl ? meta.barCls : ''}`}
          />
        ))}
      </div>
      <div className={`${styles.strengthLabel} ${meta ? meta.labelCls : ''}`}>
        {meta ? meta.label : ''}
      </div>
    </div>
  );
}
