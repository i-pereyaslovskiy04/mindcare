import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import MoodSelector from './components/Diary/MoodSelector';
import DiaryEntryForm from './components/Diary/DiaryEntryForm';
import DiaryHistoryList from './components/Diary/DiaryHistoryList';
import * as diaryApi from '../../api/diary.api';
import styles from './DiaryPage.module.css';

const HISTORY_PREVIEW_LIMIT = 4;

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

function getRealSummaryPoints(summary) {
  return (summary?.points ?? []).filter((p) => p.mood_score !== null);
}

function formatShortDate(isoDate) {
  const parts = isoDate.split('-');
  return `${parts[2]}.${parts[1]}`;
}

function formatScore(value) {
  if (value === null || value === undefined) return '—';
  return `${value}/10`;
}

function getLatestPoint(realPoints) {
  if (!realPoints.length) return null;
  return realPoints[realPoints.length - 1];
}

function getRangeLabel(realPoints) {
  if (!realPoints.length) return '—';
  const scores = realPoints.map((p) => p.mood_score);
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  if (min === max) return formatScore(min);
  return `${formatScore(min)} – ${formatScore(max)}`;
}

function getRecentMarks(realPoints, activePeriod, limit = 5) {
  return realPoints.slice(-limit).map((p) => ({
    key: p.date,
    label:
      activePeriod === 'year'
        ? `${p.label} · ${formatScore(p.mood_score)}`
        : `${formatShortDate(p.date)} · ${formatScore(p.mood_score)}`,
  }));
}

function getObservationHint(entriesCount) {
  if (entriesCount === 0)
    return 'Пока нет данных для самонаблюдения. После нескольких отметок здесь появится краткая сводка.';
  if (entriesCount === 1)
    return 'Есть первая отметка. Когда записей станет больше, здесь появится краткая сводка за период.';
  if (entriesCount <= 3)
    return 'Пока данных немного. Эти записи уже можно использовать как основу для разговора с психологом.';
  return 'Можно посмотреть, какие отметки были в выбранный период.';
}

export default function DiaryPage() {
  const [emotions, setEmotions] = useState([]);
  const [entries, setEntries] = useState([]);
  const [entriesTotal, setEntriesTotal] = useState(0);

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
        diaryApi.getDiaryEntries({ limit: HISTORY_PREVIEW_LIMIT, offset: 0 }),
      ]);
      setEmotions(emotionsData ?? []);
      setMood(todayData.mood_score ?? 5);
      setText(todayData.entry_text ?? '');
      setSelectedEmotions(todayData.emotions ?? []);
      setIsExistingEntry(todayData.mood_score !== null);
      const items = entriesData.items ?? [];
      const total = entriesData.total ?? 0;
      setEntries(items);
      setEntriesTotal(total);
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
      setMood(5);
      setText('');
      setSelectedEmotions([]);
      setIsExistingEntry(false);
    }
    // Reload preview to reflect correct data after delete.
    try {
      const entriesData = await diaryApi.getDiaryEntries({ limit: HISTORY_PREVIEW_LIMIT, offset: 0 });
      const items = entriesData.items ?? [];
      const total = entriesData.total ?? 0;
      setEntries(items);
      setEntriesTotal(total);
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
      const entriesData = await diaryApi.getDiaryEntries({ limit: HISTORY_PREVIEW_LIMIT, offset: 0 });
      const items = entriesData.items ?? [];
      const total = entriesData.total ?? 0;
      setEntries(items);
      setEntriesTotal(total);
      setShowSaved(true);
      setTimeout(() => setShowSaved(false), 2000);
      loadSummary(activePeriod);
    } catch (err) {
      setSaveError(err.message || 'Не удалось сохранить запись.');
    } finally {
      setSaving(false);
    }
  }

  const realPoints = getRealSummaryPoints(summaryData);
  const latestPoint = getLatestPoint(realPoints);
  const recentMarks = getRecentMarks(realPoints, activePeriod);

  const historyFooterLink = entriesTotal > 0
    ? <Link to="/student/diary/history">Смотреть всю историю</Link>
    : undefined;

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
                Записи помогают вспомнить самочувствие за период и обсудить это с психологом.
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
                <div data-testid="observation-summary">
                  <div className={styles.summaryGrid}>
                    <div className={styles.summaryTile}>
                      <span className={styles.summaryValue}>
                        {summaryData?.entries_count ?? 0}
                      </span>
                      <span className={styles.summaryLabel}>Отметок</span>
                    </div>
                    <div className={styles.summaryTile}>
                      <span className={styles.summaryValue}>
                        {latestPoint
                          ? activePeriod === 'year'
                            ? `${latestPoint.label} · ${formatScore(latestPoint.mood_score)}`
                            : `${formatScore(latestPoint.mood_score)} · ${formatShortDate(latestPoint.date)}`
                          : '—'}
                      </span>
                      <span className={styles.summaryLabel}>
                        {activePeriod === 'year' ? 'Последний период' : 'Последняя отметка'}
                      </span>
                    </div>
                    <div className={styles.summaryTile}>
                      <span className={styles.summaryValue}>
                        {getRangeLabel(realPoints)}
                      </span>
                      <span className={styles.summaryLabel}>Диапазон</span>
                    </div>
                  </div>
                  {recentMarks.length > 0 && (
                    <div className={styles.recentMarks}>
                      <p className={styles.recentMarksTitle}>Последние отметки</p>
                      <div className={styles.markChips}>
                        {recentMarks.map(({ key, label }) => (
                          <span key={key} className={styles.markChip}>{label}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  <p className={styles.observationHint}>
                    {getObservationHint(summaryData?.entries_count ?? 0)}
                  </p>
                </div>
              )}
            </div>
          </div>

          <div className={styles.historyCol}>
            <DiaryHistoryList
              entries={entries}
              emotionCatalog={emotions}
              onEntryUpdate={handleEntryUpdate}
              onEntryDelete={handleEntryDelete}
              footerLink={historyFooterLink}
            />
          </div>
        </div>
      )}
    </div>
  );
}
