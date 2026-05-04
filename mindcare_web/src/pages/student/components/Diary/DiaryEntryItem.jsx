import styles from './DiaryEntryItem.module.css';

const MOOD_WORDS = [
  '', 'Очень тяжело', 'Тяжело', 'Грустно', 'Так себе',
  'Нейтрально', 'Спокойно', 'Хорошо', 'Светло', 'Радостно', 'Прекрасно',
];

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('ru-RU', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
}

function getMoodColor(v) {
  if (v <= 3) return 'var(--error)';
  if (v <= 5) return '#D4891A';
  if (v <= 7) return '#8B6F47';
  return 'var(--success)';
}

export default function DiaryEntryItem({ entry }) {
  const { date, mood, emotions, note } = entry;

  return (
    <div className={styles.item}>
      <div className={styles.top}>
        <span className={styles.date}>{formatDate(date)}</span>
        <span className={styles.moodBadge} style={{ color: getMoodColor(mood) }}>
          {mood}/10 · {MOOD_WORDS[mood]}
        </span>
      </div>

      {emotions.length > 0 && (
        <div className={styles.emotionRow}>
          {emotions.map((em) => (
            <span key={em} className={styles.emotionTag}>{em}</span>
          ))}
        </div>
      )}

      {note && <p className={styles.note}>{note}</p>}
    </div>
  );
}
