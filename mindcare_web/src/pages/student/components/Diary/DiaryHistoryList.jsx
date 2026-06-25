import { useState } from 'react';
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
  // Only one action menu open at a time across the list
  const [openActionsUuid, setOpenActionsUuid] = useState(null);

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
              actionsOpen={openActionsUuid === entry.uuid}
              onActionsToggle={() =>
                setOpenActionsUuid((prev) =>
                  prev === entry.uuid ? null : entry.uuid
                )
              }
              onActionsClose={() => setOpenActionsUuid(null)}
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
