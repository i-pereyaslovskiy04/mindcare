import { useState, useEffect } from 'react';
import MoodChart from './components/MoodChart/MoodChart';
import MoodSelector from './components/Diary/MoodSelector';
import DiaryEntryForm from './components/Diary/DiaryEntryForm';
import DiaryHistoryList from './components/Diary/DiaryHistoryList';
import * as diaryApi from '../../api/diary.api';
import styles from './DiaryPage.module.css';

const HISTORY_LIMIT = 10;

const PERIOD_LABELS = {
  '14d': '14 дней',
  month: 'Месяц',
  year: 'Год',
};

function formatLocalDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function formatTodayLabel() {
  return new Date().toLocaleDateString('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

function getObservationHint(entriesCount) {
  if (entriesCount === 0) return 'Пока нет данных для графика. Добавьте несколько отметок, чтобы увидеть динамику.';
  if (entriesCount === 1) return 'Есть первая отметка. Для динамики нужно больше записей.';
  if (entriesCount <= 3) return 'Пока мало данных для тренда, но эти записи уже можно обсудить с психологом.';
  return 'Можно смотреть первые изменения за выбранный период.';
}

export default function DiaryPage() {
  const [emotions, setEmotions] = useState([]);
  const [entries, setEntries] = useState([]);
  const [entriesOffset, setEntriesOffset] = useState(HISTORY_LIMIT);
  const [entriesHasMore, setEntriesHasMore] = useState(false);
  const [entriesLoadingMore, setEntriesLoadingMore] = useState(false);
  const [entriesLoadMoreError, setEntriesLoadMoreError] = useState(null);

  // Controlled form state — synced from today API on initial load and after save
  const [mood, setMood] = useState(null);
  const [text, setText] = useState('');
  const [selectedEmotions, setSelectedEmotions] = useState([]);
  const [isExistingEntry, setIsExistingEntry] = useState(false);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showSaved, setShowSaved] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [saveError, setSaveError] = useState(null);

  // Observation / summary state — independent from main load
  const [activePeriod, setActivePeriod] = useState('14d');
  const [summaryData, setSummaryData] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState(null);

  async function loadSummary(period) {
    setSummaryLoading(true);
    setSummaryError(null);
    try {
      const data = await diaryApi.getDiarySummary(period);
      setSummaryData(data);
    } catch {
      setSummaryError('Не удалось загрузить самонаблюдение.');
    } finally {
      setSummaryLoading(false);
    }
  }

  async function loadAll() {
    setLoading(true);
    setLoadError(null);
    try {
      const [emotionsData, todayData, entriesData] = await Promise.all([
        diaryApi.getDiaryEmotions(),
        diaryApi.getTodayDiaryEntry(),
        diaryApi.getDiaryEntries({ limit: HISTORY_LIMIT, offset: 0 }),
      ]);
      setEmotions(emotionsData ?? []);
      setMood(todayData.mood_score);
      setText(todayData.entry_text ?? '');
      setSelectedEmotions(todayData.emotions ?? []);
      setIsExistingEntry(todayData.mood_score !== null);
      const items = entriesData.items ?? [];
      const total = entriesData.total ?? 0;
      setEntries(items);
      setEntriesOffset(HISTORY_LIMIT);
      setEntriesHasMore(items.length < total);
      setEntriesLoadMoreError(null);
    } catch (err) {
      setLoadError(err.message || 'Не удалось загрузить дневник.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadSummary('14d');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handlePeriodChange(period) {
    setActivePeriod(period);
    loadSummary(period);
  }

  function handleEmotionToggle(key) {
    setSelectedEmotions((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  }

  async function handleLoadMore() {
    if (entriesLoadingMore) return;
    setEntriesLoadingMore(true);
    setEntriesLoadMoreError(null);
    try {
      const data = await diaryApi.getDiaryEntries({ limit: HISTORY_LIMIT, offset: entriesOffset });
      const newItems = data.items ?? [];
      const total = data.total ?? 0;
      setEntries((prev) => [...prev, ...newItems]);
      setEntriesHasMore(entriesOffset + newItems.length < total);
      setEntriesOffset(entriesOffset + HISTORY_LIMIT);
    } catch {
      setEntriesLoadMoreError('Не удалось загрузить записи. Попробуйте ещё раз.');
    } finally {
      setEntriesLoadingMore(false);
    }
  }

  function handleEntryUpdate(updatedEntry) {
    setEntries((prev) =>
      prev.map((e) => (e.uuid === updatedEntry.uuid ? updatedEntry : e))
    );
    const todayLocal = formatLocalDate(new Date());
    if (updatedEntry.entry_date === todayLocal) {
      setMood(updatedEntry.mood_score);
      setText(updatedEntry.entry_text ?? '');
      setSelectedEmotions(updatedEntry.emotions ?? []);
      setIsExistingEntry(true);
    }
    loadSummary(activePeriod);
  }

  async function handleEntryDelete(uuid) {
    const todayLocal = formatLocalDate(new Date());
    const deleted = entries.find((e) => e.uuid === uuid);
    setEntries((prev) => prev.filter((e) => e.uuid !== uuid));
    if (deleted?.entry_date === todayLocal) {
      setMood(null);
      setText('');
      setSelectedEmotions([]);
      setIsExistingEntry(false);
    }
    // Reload page 1 to fix entriesOffset after delete so load-more stays consistent.
    try {
      const entriesData = await diaryApi.getDiaryEntries({ limit: HISTORY_LIMIT, offset: 0 });
      const items = entriesData.items ?? [];
      const total = entriesData.total ?? 0;
      setEntries(items);
      setEntriesOffset(HISTORY_LIMIT);
      setEntriesHasMore(items.length < total);
      setEntriesLoadMoreError(null);
    } catch {
      // Non-critical: list already updated optimistically above.
    }
    loadSummary(activePeriod);
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await diaryApi.saveTodayDiaryEntry({
        mood_score: mood,
        entry_text: text,
        emotions: selectedEmotions,
      });
      setMood(saved.mood_score);
      setText(saved.entry_text ?? '');
      setSelectedEmotions(saved.emotions ?? []);
      setIsExistingEntry(true);
      const entriesData = await diaryApi.getDiaryEntries({ limit: HISTORY_LIMIT, offset: 0 });
      const items = entriesData.items ?? [];
      const total = entriesData.total ?? 0;
      setEntries(items);
      setEntriesOffset(HISTORY_LIMIT);
      setEntriesHasMore(items.length < total);
      setEntriesLoadMoreError(null);
      setShowSaved(true);
      setTimeout(() => setShowSaved(false), 2000);
      loadSummary(activePeriod);
    } catch (err) {
      setSaveError(err.message || 'Не удалось сохранить запись.');
    } finally {
      setSaving(false);
    }
  }

  const chartData = (summaryData?.points ?? []).map((p) => ({
    l: p.label,
    v: p.mood_score,
    d: p.date,
  }));

  return (
    <div className={styles.page}>
      <div className={styles.labelTag}>{formatTodayLabel()}</div>
      <h1 className={styles.pageTitle}>
        Дневник <em>самочувствия</em>
      </h1>
      <p className={styles.pageSub}>
        Отмечайте состояние в удобном ритме. Даже короткие записи помогают замечать изменения и готовиться к разговору с психологом.
      </p>

      {loading ? (
        <p className={styles.loadingMsg}>Загружается…</p>
      ) : loadError ? (
        <div className={styles.errorBlock}>
          <p className={styles.errorMsg}>{loadError}</p>
          <button type="button" className={styles.retryBtn} onClick={loadAll}>
            Повторить
          </button>
        </div>
      ) : (
        <div className={styles.layout}>
          <div className={styles.formCol}>
            <MoodSelector value={mood} onChange={setMood} />
            <DiaryEntryForm
              emotions={emotions}
              text={text}
              onTextChange={setText}
              selectedEmotions={selectedEmotions}
              onEmotionToggle={handleEmotionToggle}
              moodSelected={mood !== null}
              isExistingEntry={isExistingEntry}
              saving={saving}
              showSaved={showSaved}
              saveError={saveError}
              onSave={handleSave}
            />

            {/* ── Observation card ── */}
            <div className={styles.observationCard}>
              <div className={styles.observationHeader}>
                <span className={styles.observationTitle}>Самонаблюдение</span>
              </div>
              <p className={styles.observationSub}>
                Записи помогают заметить изменения в самочувствии и обсудить их с психологом.
              </p>
              <div className={styles.periodChips}>
                {['14d', 'month', 'year'].map((p) => (
                  <button
                    key={p}
                    type="button"
                    className={
                      activePeriod === p
                        ? `${styles.periodChip} ${styles.periodChipActive}`
                        : styles.periodChip
                    }
                    onClick={() => handlePeriodChange(p)}
                  >
                    {PERIOD_LABELS[p]}
                  </button>
                ))}
              </div>
              {summaryLoading ? (
                <p className={styles.observationLoading}>Загружается…</p>
              ) : summaryError ? (
                <div className={styles.observationError}>
                  <span>{summaryError}</span>
                  <button
                    type="button"
                    className={styles.retryBtn}
                    onClick={() => loadSummary(activePeriod)}
                  >
                    Повторить
                  </button>
                </div>
              ) : (
                <>
                  <div className={styles.chartWrap}>
                    <MoodChart data={chartData} period={activePeriod} />
                  </div>
                  <p className={styles.observationHint}>
                    {getObservationHint(summaryData?.entries_count ?? 0)}
                  </p>
                </>
              )}
            </div>
          </div>

          <div className={styles.historyCol}>
            <DiaryHistoryList
              entries={entries}
              emotionCatalog={emotions}
              hasMore={entriesHasMore}
              loadingMore={entriesLoadingMore}
              onLoadMore={handleLoadMore}
              loadMoreError={entriesLoadMoreError}
              onEntryUpdate={handleEntryUpdate}
              onEntryDelete={handleEntryDelete}
            />
          </div>
        </div>
      )}
    </div>
  );
}
