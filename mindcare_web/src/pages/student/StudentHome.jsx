import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';
import MoodChart from './components/MoodChart/MoodChart';
import StatCard from './components/StatCard/StatCard';
import Icon from './components/Icon';
import styles from './StudentHome.module.css';

const MOOD_WORDS = [
  '', 'Очень тяжело', 'Тяжело', 'Грустно', 'Так себе',
  'Нейтрально', 'Спокойно', 'Хорошо', 'Светло', 'Радостно', 'Прекрасно',
];

const CHART_DATA = [
  { l: 'Пн', v: 5 }, { l: 'Вт', v: 4 }, { l: 'Ср', v: 6 }, { l: 'Чт', v: 5 },
  { l: 'Пт', v: 7 }, { l: 'Сб', v: 8 }, { l: 'Вс', v: 6 }, { l: 'Пн', v: 7 },
  { l: 'Вт', v: 5 }, { l: 'Ср', v: 6 }, { l: 'Чт', v: 7 }, { l: 'Пт', v: 8 },
  { l: 'Сб', v: 7 },
];

const QUICK_ACTIONS = [
  { icon: 'diary',    title: 'Записать настроение',        desc: '~2 минуты',           to: '/student/diary' },
  { icon: 'tests',    title: 'Пройти тест GAD-7',          desc: 'Уровень тревоги · 5 мин', to: '/student/tests' },
  { icon: 'tasks',    title: 'Задания психолога',           desc: '2 в работе',           to: '/student/tasks', badge: '2' },
  { icon: 'leaf',     title: '5-минутная практика дыхания', desc: 'Аудио · для тревожности', to: '/student/articles' },
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
  const navigate = useNavigate();
  const [moodValue, setMoodValue] = useState(7);

  const chartData = [...CHART_DATA, { l: 'Сегодня', v: moodValue }];
  const todayLabel = formatTodayLabel();

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

        {/* dark mood card */}
        <div className={styles.moodCard}>
          <div className={styles.moodCardTop}>
            <div>
              <div className={styles.moodCardTagLabel}>Состояние сегодня</div>
              <div className={styles.moodCardTitle}>{MOOD_WORDS[moodValue]}</div>
              <div className={styles.moodCardHint}>
                Одно прикосновение к шкале — и день уже отмечен.
              </div>
            </div>
            <div className={styles.moodScore}>
              <div className={styles.moodScoreNum}>{moodValue}</div>
              <div className={styles.moodScoreLabel}>из 10</div>
            </div>
          </div>

          <div>
            <input
              type="range"
              min="1"
              max="10"
              value={moodValue}
              onChange={(e) => setMoodValue(Number(e.target.value))}
              className={styles.moodSlider}
            />
            <div className={styles.moodScaleLabels}>
              <span>тяжело</span>
              <span>нейтрально</span>
              <span>светло</span>
            </div>
          </div>

          <div className={styles.moodButtons}>
            <button
              className={styles.btnLatte}
              onClick={() => navigate('/student/diary')}
            >
              Записать в дневник
            </button>
            <button
              className={styles.btnGhostDark}
              onClick={() => navigate('/student/chat')}
            >
              Написать психологу
            </button>
          </div>
        </div>

        {/* next session card */}
        <div className={styles.sessionCard}>
          <div className={styles.labelTagMuted}>Ближайшая сессия</div>
          <div>
            <div className={styles.sessionDate}>Пятница, 30 апреля</div>
            <div className={styles.sessionTime}>15:00 · онлайн (видео)</div>
          </div>
          <div className={styles.psychCard}>
            <div className={styles.psychAvatar}>МК</div>
            <div>
              <div className={styles.psychName}>Мария Ковалёва</div>
              <div className={styles.psychRole}>Клинический психолог</div>
            </div>
          </div>
          <button
            className={styles.btnSoft}
            onClick={() => navigate('/student/calendar')}
          >
            <Icon name="video" size={14} /> Подключиться
          </button>
        </div>
      </div>

      {/* ---- stat tiles ---- */}
      <div className={`${styles.grid} ${styles.g3}`} style={{ marginBottom: 24 }}>
        <StatCard label="Тревожность" value="3.2" unit="/10" trend="↓ 18% за неделю" />
        <StatCard label="Записей в дневнике" value="12" unit="за месяц" trend="↑ постоянство растёт" />
        <StatCard label="Сон" value="7.4" unit="часа" trend="↓ 0.6ч от нормы" trendDown />
      </div>

      {/* ---- mood chart + quick actions ---- */}
      <div className={`${styles.grid} ${styles.g21}`}>
        <div className={styles.card}>
          <div className={styles.chartHeader}>
            <h2 className={styles.sectionTitle}>Динамика настроения</h2>
            <div className={styles.periodChips}>
              <button className={styles.chipActive}>14 дней</button>
              <button className={styles.chip}>Месяц</button>
              <button className={styles.chip}>Год</button>
            </div>
          </div>
          <MoodChart data={chartData} height={160} />
        </div>

        <div className={styles.card}>
          <h2 className={styles.sectionTitle}>Быстрые действия</h2>
          <div>
            {QUICK_ACTIONS.map((item) => (
              <div
                key={item.icon}
                className={styles.liRow}
                role="button"
                tabIndex={0}
                onClick={() => navigate(item.to)}
                onKeyDown={(e) => e.key === 'Enter' && navigate(item.to)}
              >
                <div className={styles.liIcon}>
                  <Icon name={item.icon} size={18} />
                </div>
                <div>
                  <div className={styles.liTitle}>{item.title}</div>
                  <div className={styles.liDesc}>{item.desc}</div>
                </div>
                {item.badge
                  ? <span className={styles.liBadge}>{item.badge}</span>
                  : <span className={styles.liArrow}><Icon name="arrow-right" size={16} /></span>
                }
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
