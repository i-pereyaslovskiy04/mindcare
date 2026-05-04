import { useState } from 'react';
import MoodSelector from './components/Diary/MoodSelector';
import DiaryEntryForm from './components/Diary/DiaryEntryForm';
import DiaryHistoryList from './components/Diary/DiaryHistoryList';
import styles from './DiaryPage.module.css';

const MOCK_ENTRIES = [
  {
    id: 1,
    date: '2026-05-03',
    mood: 7,
    emotions: ['спокойно', 'сосредоточенно'],
    note: 'Сегодня удалось поработать в тишине. Чувствую прогресс.',
  },
  {
    id: 2,
    date: '2026-05-02',
    mood: 5,
    emotions: ['тревожно', 'устало'],
    note: 'Было много задач, не успевала. Ощущение усталости к вечеру.',
  },
  {
    id: 3,
    date: '2026-04-30',
    mood: 8,
    emotions: ['радостно', 'легко'],
    note: 'Встреча с подругой подняла настроение. День прошёл хорошо.',
  },
  {
    id: 4,
    date: '2026-04-29',
    mood: 4,
    emotions: ['грустно'],
    note: '',
  },
];

function formatTodayLabel() {
  return new Date().toLocaleDateString('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

export default function DiaryPage() {
  const [mood, setMood] = useState(6);
  const [entries, setEntries] = useState(MOCK_ENTRIES);

  function handleSave({ note, emotions }) {
    const newEntry = {
      id: Date.now(),
      date: new Date().toISOString().slice(0, 10),
      mood,
      emotions,
      note,
    };
    setEntries((prev) => [newEntry, ...prev]);
  }

  return (
    <div className={styles.page}>
      <div className={styles.labelTag}>{formatTodayLabel()}</div>
      <h1 className={styles.pageTitle}>
        Дневник <em>состояния</em>
      </h1>
      <p className={styles.pageSub}>
        Фиксируйте настроение каждый день — это помогает замечать паттерны
        и работать с ними вместе с психологом.
      </p>

      <div className={styles.layout}>
        <div className={styles.formCol}>
          <MoodSelector value={mood} onChange={setMood} />
          <DiaryEntryForm onSave={handleSave} />
        </div>
        <div className={styles.historyCol}>
          <DiaryHistoryList entries={entries} />
        </div>
      </div>
    </div>
  );
}
