import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';
import { getDiarySummary, getTodayDiaryEntry, getDiaryEmotions } from '../../api/diary.api';
import StatCard from './components/StatCard/StatCard';
import Icon from '../../components/Icon/Icon';
import styles from './StudentHome.module.css';

const MOOD_WORDS = [
  '', 'Очень тяжело', 'Тяжело', 'Грустно', 'Так себе',
  'Нейтрально', 'Спокойно', 'Хорошо', 'Светло', 'Радостно', 'Прекрасно',
];

const QUICK_ACTIONS = [
  { icon: 'diary', title: 'Отметить состояние', desc: 'Записать сегодняшнее состояние', to: '/student/diary'     },
  { icon: 'chat',  title: 'Написать психологу', desc: 'Открыть переписку',              to: '/student/chat'      },
  { icon: 'leaf',  title: 'Материалы',          desc: 'Статьи и упражнения',            to: '/student/materials' },
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
  // null = not yet loaded; { entriesCount, avgMood, realPointsCount } = loaded
  const [obs14d, setObs14d] = useState(null);
  // undefined = loading, null = no entry or API error, object = entry with mood_score set
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

      {/* ---- main row: left = mood+obs, right = session+actions ---- */}
      <div className={`${styles.grid} ${styles.g21}`} style={{ marginBottom: 24 }}>

        {/* LEFT: dark mood card + self-observation summary */}
        <div className={styles.leftCol}>

          {/* dark mood card — shows real today diary entry */}
          <div className={styles.moodCard}>
            <div className={styles.moodCardTagLabel}>Состояние сегодня</div>

            {todayLoading ? (
              <div className={styles.moodCardLoading}>Загрузка…</div>
            ) : hasTodayEntry ? (
              <>
                <div className={styles.moodCardTop}>
                  <div className={styles.moodCardTitle}>
                    {MOOD_WORDS[todayEntry.mood_score]}
                  </div>
                  <div className={styles.moodScore}>
                    <div className={styles.moodScoreNum}>{todayEntry.mood_score}</div>
                    <div className={styles.moodScoreLabel}>из 10</div>
                  </div>
                </div>
                {todayEntry.emotions && todayEntry.emotions.length > 0 && (
                  <div className={styles.moodEmotions}>
                    {todayEntry.emotions.map((key) => {
                      const found = emotionCatalog.find((e) => e.key === key);
                      return (
                        <span key={key} className={styles.moodEmotionTag}>
                          {found ? found.label : key}
                        </span>
                      );
                    })}
                  </div>
                )}
                <div className={styles.moodButtons}>
                  <Link to="/student/diary" className={styles.btnLatte}>
                    Дополнить запись
                  </Link>
                  <Link to="/student/diary" className={styles.btnGhostDark}>
                    Открыть дневник
                  </Link>
                </div>
              </>
            ) : (
              <>
                <div className={styles.moodCardEmpty}>
                  Сегодня состояние ещё не отмечено.
                  Короткая отметка занимает меньше минуты.
                </div>
                <div className={styles.moodButtons}>
                  <Link to="/student/diary" className={styles.btnLatte}>
                    Отметить состояние
                  </Link>
                  <Link to="/student/chat" className={styles.btnGhostDark}>
                    Написать психологу
                  </Link>
                </div>
              </>
            )}
          </div>

          {/* self-observation summary — always fixed to 14-day window */}
          <div className={styles.card}>
            <div className={styles.labelTagMuted}>Самонаблюдение · 14 дней</div>
            {obs14d === null ? (
              <div className={styles.obsLoading}>Загрузка…</div>
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
                <Link to="/student/diary" className={styles.obsAction}>
                  Открыть дневник
                </Link>
              </>
            )}
          </div>
        </div>

        {/* RIGHT: session placeholder + quick actions */}
        <div className={styles.rightCol}>

          {/* session placeholder — appointments backend not yet implemented */}
          <div className={styles.sessionCard}>
            <div className={styles.labelTagMuted}>Ближайшая сессия</div>
            <div className={styles.sessionEmpty}>
              Пока нет данных о предстоящей сессии.
            </div>
            <Link to="/student/chat" className={styles.btnSoft}>
              Написать психологу
            </Link>
          </div>

          {/* quick actions */}
          <div className={styles.card}>
            <h2 className={styles.sectionTitle}>Быстрые действия</h2>
            <div>
              {QUICK_ACTIONS.map((item) => (
                <Link
                  key={item.icon}
                  to={item.to}
                  className={styles.liRow}
                >
                  <div className={styles.liIcon}>
                    <Icon name={item.icon} size={18} />
                  </div>
                  <div>
                    <div className={styles.liTitle}>{item.title}</div>
                    <div className={styles.liDesc}>{item.desc}</div>
                  </div>
                  <span className={styles.liArrow}><Icon name="arrow-right" size={16} /></span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ---- stat tiles — real diary data only ---- */}
      <div className={`${styles.grid} ${styles.g2}`} style={{ marginBottom: 24 }}>
        <StatCard
          label="Записей в дневнике"
          value={obs14d !== null ? String(obs14d.entriesCount) : '—'}
          unit="за 14 дней"
          trend="↑ постоянство растёт"
        />
        <StatCard
          label="Запись сегодня"
          value={todayLoading ? '…' : hasTodayEntry ? 'Есть' : 'Нет'}
          unit=""
          trend={hasTodayEntry ? '✓ отмечено сегодня' : 'ещё не заполнено'}
          trendDown={!hasTodayEntry && !todayLoading}
        />
      </div>
    </div>
  );
}
