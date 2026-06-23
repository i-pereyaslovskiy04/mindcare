import { useState, useEffect } from 'react';
import MoodSelector from './components/Diary/MoodSelector';
import DiaryEntryForm from './components/Diary/DiaryEntryForm';
import DiaryHistoryList from './components/Diary/DiaryHistoryList';
import * as diaryApi from '../../api/diary.api';
import styles from './DiaryPage.module.css';

function formatTodayLabel() {
  return new Date().toLocaleDateString('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

export default function DiaryPage() {
  const [emotions, setEmotions] = useState([]);
  const [entries, setEntries] = useState([]);

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

  async function loadAll() {
    setLoading(true);
    setLoadError(null);
    try {
      const [emotionsData, todayData, entriesData] = await Promise.all([
        diaryApi.getDiaryEmotions(),
        diaryApi.getTodayDiaryEntry(),
        diaryApi.getDiaryEntries({ limit: 10, offset: 0 }),
      ]);
      setEmotions(emotionsData ?? []);
      setMood(todayData.mood_score);
      setText(todayData.entry_text ?? '');
      setSelectedEmotions(todayData.emotions ?? []);
      setIsExistingEntry(todayData.mood_score !== null);
      setEntries(entriesData.items ?? []);
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

  function handleEmotionToggle(key) {
    setSelectedEmotions((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
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
      const entriesData = await diaryApi.getDiaryEntries({ limit: 10, offset: 0 });
      setEntries(entriesData.items ?? []);
      setShowSaved(true);
      setTimeout(() => setShowSaved(false), 2000);
    } catch (err) {
      setSaveError(err.message || 'Не удалось сохранить запись.');
    } finally {
      setSaving(false);
    }
  }

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
          </div>
          <div className={styles.historyCol}>
            <DiaryHistoryList entries={entries} emotionCatalog={emotions} />
          </div>
        </div>
      )}
    </div>
  );
}
