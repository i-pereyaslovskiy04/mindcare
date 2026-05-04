import DiaryEntryItem from './DiaryEntryItem';
import styles from './DiaryHistoryList.module.css';

export default function DiaryHistoryList({ entries }) {
  return (
    <div className={styles.panel}>
      <h2 className={styles.title}>История записей</h2>
      {entries.length === 0 ? (
        <p className={styles.empty}>Записей пока нет. Сделайте первую запись!</p>
      ) : (
        <div className={styles.list}>
          {entries.map((entry) => (
            <DiaryEntryItem key={entry.id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  );
}
