import styles from './MoodSelector.module.css';

const MOOD_WORDS = [
  '', 'Очень тяжело', 'Тяжело', 'Грустно', 'Так себе',
  'Нейтрально', 'Спокойно', 'Хорошо', 'Светло', 'Радостно', 'Прекрасно',
];

export default function MoodSelector({ value, onChange }) {
  const isSet = value !== null && value !== undefined;
  const displayValue = isSet ? value : 5;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div>
          <div className={styles.tagLabel}>Как вы сейчас?</div>
          <div className={styles.moodWord}>
            {isSet ? MOOD_WORDS[value] : 'Выберите настроение'}
          </div>
        </div>
        <div className={styles.score}>
          <span className={styles.scoreNum}>{isSet ? value : '—'}</span>
          <span className={styles.scoreLabel}>из 10</span>
        </div>
      </div>

      <input
        type="range"
        min="1"
        max="10"
        value={displayValue}
        onChange={(e) => onChange(Number(e.target.value))}
        className={styles.slider}
        aria-label="Уровень настроения"
      />
      <div className={styles.scaleLabels}>
        <span>1 · тяжело</span>
        <span>5–6 · нейтрально</span>
        <span>10 · светло</span>
      </div>
    </div>
  );
}
