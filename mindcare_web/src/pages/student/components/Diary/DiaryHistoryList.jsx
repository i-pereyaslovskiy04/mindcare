import DiaryEntryItem from './DiaryEntryItem';
import styles from './DiaryHistoryList.module.css';

export default function DiaryHistoryList({
  entries,
  emotionCatalog = [],
  hasMore = false,
  loadingMore = false,
  onLoadMore,
  loadMoreError = null,
  onEntryUpdate,
  onEntryDelete,
  footerLink,
  hideTitle = false,
}) {
  return (
    <div className={styles.panel}>
      {!hideTitle && <h2 className={styles.title}>История записей</h2>}
      {entries.length === 0 ? (
        <p className={styles.empty}>Здесь появятся ваши записи.</p>
      ) : (
        <div className={styles.list}>
          {entries.map((entry) => (
            <DiaryEntryItem
              key={entry.uuid}
              entry={entry}
              emotionCatalog={emotionCatalog}
              onUpdate={onEntryUpdate}
              onDelete={onEntryDelete}
            />
          ))}
        </div>
      )}
      {loadMoreError && (
        <p className={styles.loadMoreError}>{loadMoreError}</p>
      )}
      {hasMore && (
        <button
          type="button"
          className={styles.loadMoreBtn}
          onClick={onLoadMore}
          disabled={loadingMore}
        >
          {loadingMore ? 'Загружаем…' : 'Загрузить ещё'}
        </button>
      )}
      {footerLink != null && (
        <div className={styles.footerLink}>{footerLink}</div>
      )}
    </div>
  );
}
