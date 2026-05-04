import styles from './MoodSelector.module.css';

const MOOD_WORDS = [
  '', 'Очень тяжело', 'Тяжело', 'Грустно', 'Так себе',
  'Нейтрально', 'Спокойно', 'Хорошо', 'Светло', 'Радостно', 'Прекрасно',
];

export default function MoodSelector({ value, onChange }) {
  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div>
          <div className={styles.tagLabel}>Как вы сейчас?</div>
          <div className={styles.moodWord}>{MOOD_WORDS[value]}</div>
        </div>
        <div className={styles.score}>
          <span className={styles.scoreNum}>{value}</span>
          <span className={styles.scoreLabel}>из 10</span>
        </div>
      </div>

      <input
        type="range"
        min="1"
        max="10"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className={styles.slider}
        aria-label="Уровень настроения"
      />
      <div className={styles.scaleLabels}>
        <span>тяжело</span>
        <span>нейтрально</span>
        <span>светло</span>
      </div>
    </div>
  );
}
