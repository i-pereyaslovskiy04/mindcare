import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import DiaryHistoryList from './components/Diary/DiaryHistoryList';
import * as diaryApi from '../../api/diary.api';
import styles from './DiaryHistoryPage.module.css';

const HISTORY_LIMIT = 10;

export default function DiaryHistoryPage() {
  const [emotions, setEmotions] = useState([]);
  const [entries, setEntries] = useState([]);
  const [offset, setOffset] = useState(HISTORY_LIMIT);
  const [hasMore, setHasMore] = useState(false);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState(null);

  async function loadHistory() {
    setLoading(true);
    setLoadError(null);
    try {
      const [emotionsData, entriesData] = await Promise.all([
        diaryApi.getDiaryEmotions(),
        diaryApi.getDiaryEntries({ limit: HISTORY_LIMIT, offset: 0 }),
      ]);
      setEmotions(emotionsData ?? []);
      const items = entriesData.items ?? [];
      const newTotal = entriesData.total ?? 0;
      setEntries(items);
      setOffset(HISTORY_LIMIT);
      setHasMore(items.length < newTotal);
      setLoadMoreError(null);
    } catch (err) {
      setLoadError(err.message || 'Не удалось загрузить историю записей.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleLoadMore() {
    if (loadingMore) return;
    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const data = await diaryApi.getDiaryEntries({ limit: HISTORY_LIMIT, offset });
      const newItems = data.items ?? [];
      const newTotal = data.total ?? 0;
      setEntries((prev) => [...prev, ...newItems]);
      setHasMore(offset + newItems.length < newTotal);
      setOffset((prev) => prev + HISTORY_LIMIT);
    } catch {
      setLoadMoreError('Не удалось загрузить записи. Попробуйте ещё раз.');
    } finally {
      setLoadingMore(false);
    }
  }

  function handleEntryUpdate(updatedEntry) {
    setEntries((prev) =>
      prev.map((e) => (e.uuid === updatedEntry.uuid ? updatedEntry : e))
    );
  }

  async function handleEntryDelete(uuid) {
    setEntries((prev) => prev.filter((e) => e.uuid !== uuid));
    try {
      const entriesData = await diaryApi.getDiaryEntries({ limit: HISTORY_LIMIT, offset: 0 });
      const items = entriesData.items ?? [];
      const newTotal = entriesData.total ?? 0;
      setEntries(items);
      setOffset(HISTORY_LIMIT);
      setHasMore(items.length < newTotal);
      setLoadMoreError(null);
    } catch {
      // optimistic removal already applied
    }
  }

  return (
    <div className={styles.page}>
      <p className={styles.breadcrumb}>Личный кабинет / Дневник состояния / История</p>
      <div className={styles.header}>
        <h1 className={styles.pageTitle}>История записей</h1>
        <Link to="/student/diary" className={styles.backLink}>
          ← Вернуться к дневнику
        </Link>
      </div>
      <p className={styles.pageSub}>
        Здесь собраны все ваши записи. Их можно редактировать или удалить.
      </p>

      {loading ? (
        <p className={styles.loadingMsg}>Загружается…</p>
      ) : loadError ? (
        <div className={styles.errorBlock}>
          <p className={styles.errorMsg}>{loadError}</p>
          <button type="button" className={styles.retryBtn} onClick={loadHistory}>
            Повторить
          </button>
        </div>
      ) : (
        <DiaryHistoryList
          entries={entries}
          emotionCatalog={emotions}
          hasMore={hasMore}
          loadingMore={loadingMore}
          onLoadMore={handleLoadMore}
          loadMoreError={loadMoreError}
          onEntryUpdate={handleEntryUpdate}
          onEntryDelete={handleEntryDelete}
          hideTitle
        />
      )}
    </div>
  );
}
