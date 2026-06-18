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

function getEmotionLabel(key, catalog) {
  const found = catalog.find((e) => e.key === key);
  return found ? found.label : key;
}

export default function DiaryEntryItem({ entry, emotionCatalog = [] }) {
  const { entry_date, mood_score, emotions, entry_text } = entry;

  return (
    <div className={styles.item}>
      <div className={styles.top}>
        <span className={styles.date}>{formatDate(entry_date)}</span>
        <span className={styles.moodBadge} style={{ color: getMoodColor(mood_score) }}>
          {mood_score}/10 · {MOOD_WORDS[mood_score]}
        </span>
      </div>

      {emotions && emotions.length > 0 && (
        <div className={styles.emotionRow}>
          {emotions.map((key) => (
            <span key={key} className={styles.emotionTag}>
              {getEmotionLabel(key, emotionCatalog)}
            </span>
          ))}
        </div>
      )}

      {entry_text && <p className={styles.note}>{entry_text}</p>}
    </div>
  );
}
