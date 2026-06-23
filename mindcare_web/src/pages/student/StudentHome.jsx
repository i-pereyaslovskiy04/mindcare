import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';
import { getDiarySummary, getTodayDiaryEntry } from '../../api/diary.api';
import MoodChart from './components/MoodChart/MoodChart';
import StatCard from './components/StatCard/StatCard';
import Icon from '../../components/Icon/Icon';
import styles from './StudentHome.module.css';

const MOOD_WORDS = [
  '', 'Очень тяжело', 'Тяжело', 'Грустно', 'Так себе',
  'Нейтрально', 'Спокойно', 'Хорошо', 'Светло', 'Радостно', 'Прекрасно',
];

const MOOD_PERIODS = [
  { key: '14d',   label: '14 дней' },
  { key: 'month', label: 'Месяц'   },
  { key: 'year',  label: 'Год'     },
];

const QUICK_ACTIONS = [
  { icon: 'diary', title: 'Дневник настроения', desc: 'Записать сегодняшнее состояние', to: '/student/diary'    },
  { icon: 'chat',  title: 'Написать психологу', desc: 'Открыть переписку',              to: '/student/chat'     },
  { icon: 'leaf',  title: 'Материалы',          desc: 'Статьи и упражнения',            to: '/student/articles' },
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

export default function StudentHome() {
  const { user } = useAuth();
  const [activePeriod, setActivePeriod] = useState('14d');
  const [chartData, setChartData] = useState([]);
  const [entriesCount, setEntriesCount] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  // undefined = loading, null = no entry today or API error, object = entry with mood_score set
  const [todayEntry, setTodayEntry] = useState(undefined);
  const todayLabel = formatTodayLabel();

  useEffect(() => {
    getTodayDiaryEntry()
      .then((data) => {
        setTodayEntry(data.mood_score !== null ? data : null);
      })
      .catch(() => {
        setTodayEntry(null);
      });
  }, []);

  useEffect(() => {
    setSummaryLoading(true);
    getDiarySummary(activePeriod)
      .then((data) => {
        setChartData(
          (data.points || []).map((p) => ({ l: p.label, v: p.mood_score, d: p.date }))
        );
        setEntriesCount(data.entries_count ?? null);
      })
      .catch(() => {
        setChartData([]);
        setEntriesCount(null);
      })
      .finally(() => setSummaryLoading(false));
  }, [activePeriod]);

  const todayLoading = todayEntry === undefined;
  const hasTodayEntry = todayEntry !== null && todayEntry !== undefined;

  return (
    <div className={styles.page}>
      <div className={styles.labelTag}>{todayLabel}</div>
      <h1 className={styles.pageTitle}>
        Здравствуйте, <em>{getFirstName(user?.name)}</em>
      </h1>
      <p className={styles.pageSub}>
        Сегодня хороший день, чтобы прислушаться к себе. Сделайте короткую запись
        о настроении или загляните к материалам.
      </p>

      {/* ---- mood + session row ---- */}
      <div className={`${styles.grid} ${styles.g21}`} style={{ marginBottom: 18 }}>

        {/* dark mood card — shows real today diary entry from API */}
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
              <div className={styles.moodButtons}>
                <Link to="/student/diary" className={styles.btnLatte}>
                  Дополнить запись
                </Link>
              </div>
            </>
          ) : (
            <>
              <div className={styles.moodCardEmpty}>
                Сегодня состояние ещё не отмечено.
                Сделайте короткую запись — это займёт меньше минуты.
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
      </div>

      {/* ---- stat tiles — real diary data only ---- */}
      <div className={`${styles.grid} ${styles.g2}`} style={{ marginBottom: 24 }}>
        <StatCard
          label="Записей в дневнике"
          value={entriesCount !== null ? String(entriesCount) : '—'}
          unit="за период"
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

      {/* ---- mood chart + quick actions ---- */}
      <div className={`${styles.grid} ${styles.g21}`}>
        <div className={styles.card}>
          <div className={styles.chartHeader}>
            <h2 className={styles.sectionTitle}>Динамика настроения</h2>
            <div className={styles.periodChips}>
              {MOOD_PERIODS.map((period) => (
                <button
                  key={period.key}
                  type="button"
                  className={activePeriod === period.key ? styles.chipActive : styles.chip}
                  aria-pressed={activePeriod === period.key}
                  onClick={() => setActivePeriod(period.key)}
                >
                  {period.label}
                </button>
              ))}
            </div>
          </div>
          <MoodChart data={summaryLoading ? [] : chartData} period={activePeriod} height={160} />
        </div>

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
  );
}
