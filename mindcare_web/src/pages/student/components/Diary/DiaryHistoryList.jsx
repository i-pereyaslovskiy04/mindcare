import DiaryEntryItem from './DiaryEntryItem';
import styles from './DiaryHistoryList.module.css';

export default function DiaryHistoryList({ entries, emotionCatalog = [] }) {
  return (
    <div className={styles.panel}>
      <h2 className={styles.title}>История записей</h2>
      {entries.length === 0 ? (
        <p className={styles.empty}>Здесь появятся ваши записи.</p>
      ) : (
        <div className={styles.list}>
          {entries.map((entry) => (
            <DiaryEntryItem key={entry.uuid} entry={entry} emotionCatalog={emotionCatalog} />
          ))}
        </div>
      )}
    </div>
  );
}
