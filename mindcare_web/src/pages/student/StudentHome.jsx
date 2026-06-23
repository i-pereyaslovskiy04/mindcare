import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';
import { getDiarySummary, getTodayDiaryEntry, getDiaryEmotions } from '../../api/diary.api';
import styles from './StudentHome.module.css';

const MOOD_WORDS = [
  '', 'Очень тяжело', 'Тяжело', 'Грустно', 'Так себе',
  'Нейтрально', 'Спокойно', 'Хорошо', 'Светло', 'Радостно', 'Прекрасно',
];


function formatTodayLabel() {
  return new Date().toLocaleDateString('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

function getFirstName(fullName) {
  if (!fullName) return 'Студент';
  return fullName.trim().split(' ')[0];
}

function plural(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'запись';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'записи';
  return 'записей';
}

function getInsightText(count) {
  if (count === 0) return 'Здесь появится динамика после первых отметок.';
  if (count <= 3) return 'Пока мало данных для тренда, но записи уже можно обсудить с психологом.';
  return 'Можно смотреть первые изменения.';
}

export default function StudentHome() {
  const { user } = useAuth();
  const [obs14d, setObs14d] = useState(null);
  const [todayEntry, setTodayEntry] = useState(undefined);
  const [emotionCatalog, setEmotionCatalog] = useState([]);
  const todayLabel = formatTodayLabel();

  useEffect(() => {
    getTodayDiaryEntry()
      .then((data) => {
        setTodayEntry(data.mood_score !== null ? data : null);
      })
      .catch(() => setTodayEntry(null));
  }, []);

  useEffect(() => {
    getDiaryEmotions()
      .then((data) => setEmotionCatalog(data || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    getDiarySummary('14d')
      .then((data) => {
        const nonNull = (data.points || []).filter((p) => p.mood_score != null);
        const avg = nonNull.length > 0
          ? Number((nonNull.reduce((s, p) => s + p.mood_score, 0) / nonNull.length).toFixed(1))
          : null;
        setObs14d({
          entriesCount: data.entries_count ?? 0,
          avgMood: avg,
          realPointsCount: nonNull.length,
        });
      })
      .catch(() => {
        setObs14d({ entriesCount: 0, avgMood: null, realPointsCount: 0 });
      });
  }, []);

  const todayLoading = todayEntry === undefined;
  const hasTodayEntry = todayEntry !== null && todayEntry !== undefined;

  return (
    <div className={styles.page}>
      <div className={styles.labelTag}>{todayLabel}</div>
      <h1 className={styles.pageTitle}>
        Здравствуйте, <em>{getFirstName(user?.name)}</em>
      </h1>
      <p className={styles.pageSub}>
        Можно сделать короткую отметку о состоянии или перейти к материалам.
      </p>

      <div className={styles.homeDashboard}>

        {/* ── LEFT: wellbeing panel ── */}
        <div className={styles.wellbeingPanel}>
          <h2 className={styles.panelTitle}>Моё состояние</h2>

          {/* section: today */}
          <div className={styles.panelSection}>
            <div className={styles.sectionLabel}>Состояние сегодня</div>

            {todayLoading ? (
              <div className={styles.stateLoading}>Загрузка…</div>
            ) : hasTodayEntry ? (
              <>
                <div className={styles.moodRow}>
                  <div className={styles.moodScoreBlock}>
                    <span className={styles.moodScoreNum}>{todayEntry.mood_score}</span>
                    <span className={styles.moodScoreOf}>/10</span>
                  </div>
                  <div className={styles.moodWord}>{MOOD_WORDS[todayEntry.mood_score]}</div>
                </div>
                {todayEntry.emotions && todayEntry.emotions.length > 0 && (
                  <div className={styles.emotionChips}>
                    {todayEntry.emotions.map((key) => {
                      const found = emotionCatalog.find((e) => e.key === key);
                      return (
                        <span key={key} className={styles.emotionChip}>
                          {found ? found.label : key}
                        </span>
                      );
                    })}
                  </div>
                )}
                <div className={styles.sectionActions}>
                  <Link to="/student/diary" className={styles.btnPrimary}>
                    Дополнить запись
                  </Link>
                  <Link to="/student/diary" className={styles.btnGhost}>
                    Открыть дневник
                  </Link>
                </div>
              </>
            ) : (
              <>
                <div className={styles.stateEmpty}>
                  Сегодня состояние ещё не отмечено.
                  Короткая отметка занимает меньше минуты.
                </div>
                <div className={styles.sectionActions}>
                  <Link to="/student/diary" className={styles.btnPrimary}>
                    Отметить состояние
                  </Link>
                </div>
              </>
            )}
          </div>

          {/* section: self-observation */}
          <div className={styles.panelSection}>
            <div className={styles.sectionLabel}>Самонаблюдение · 14 дней</div>
            {obs14d === null ? (
              <div className={styles.stateLoading}>Загрузка…</div>
            ) : (
              <>
                <div className={styles.obsMeta}>
                  <span className={styles.obsCount}>
                    {obs14d.entriesCount} {plural(obs14d.entriesCount)}
                  </span>
                  {obs14d.avgMood !== null && (
                    <span className={styles.obsAvg}>· среднее {obs14d.avgMood}/10</span>
                  )}
                </div>
                <div className={styles.obsInsight}>{getInsightText(obs14d.entriesCount)}</div>
                <Link to="/student/diary" className={styles.obsLink}>
                  Открыть дневник
                </Link>
              </>
            )}
          </div>

          {/* mini stats row */}
          <div className={styles.miniStatsRow}>
            <div className={styles.miniStat}>
              <div className={styles.miniStatValue}>
                {obs14d !== null ? obs14d.entriesCount : '—'}
              </div>
              <div className={styles.miniStatLabel}>Записей за 14 дней</div>
            </div>
            <div className={styles.miniStat}>
              <div className={styles.miniStatValue}>
                {todayLoading ? '…' : hasTodayEntry ? 'Есть' : 'Нет'}
              </div>
              <div className={styles.miniStatLabel}>Запись сегодня</div>
            </div>
          </div>
        </div>

        {/* ── RIGHT: support panel ── */}
        <div className={styles.supportPanel}>
          <h2 className={styles.panelTitle}>Поддержка</h2>

          {/* section: psychologist */}
          <div className={styles.panelSection}>
            <div className={styles.sectionLabel}>Психолог</div>
            <div className={styles.supportText}>
              Предстоящая сессия пока не назначена.
              Можно написать психологу в чат.
            </div>
            <div className={styles.sectionActions}>
              <Link to="/student/chat" className={styles.btnSoft}>
                Написать психологу
              </Link>
            </div>
          </div>

          {/* section: materials */}
          <div className={styles.panelSection}>
            <div className={styles.sectionLabel}>Материалы</div>
            <div className={styles.supportText}>
              Статьи и упражнения для самостоятельной работы.
            </div>
            <div className={styles.sectionActions}>
              <Link to="/student/materials" className={styles.btnGhost}>
                Открыть материалы
              </Link>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
