import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';
import { getDiarySummary, getTodayDiaryEntry, getDiaryEmotions } from '../../api/diary.api';
import useUpcomingAppointments from '../../features/appointments/hooks/useUpcomingAppointments';
import useOpenAssignmentsPreview from '../../features/assignments/hooks/useOpenAssignmentsPreview';
import { formatDueDate, formatMoment } from '../../features/assignments/lib/assignmentFormat';
import { NEUTRAL_GREETING } from '../../shared/lib/greeting';
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

const MEETING_STATUS = {
  pending_confirmation: 'ожидает подтверждения',
  confirmed: 'подтверждена',
};

function UpcomingMeetings() {
  const { items, loading, error } = useUpcomingAppointments();
  return (
    <section className={styles.actionCard} aria-labelledby="home-meetings-title">
      <h2 id="home-meetings-title" className={styles.cardTitle}>Ближайшие встречи</h2>
      {loading && <p className={styles.cardText}>Загружается…</p>}
      {!loading && error && <p className={styles.cardText}>Не удалось загрузить встречи.</p>}
      {!loading && !error && items.length === 0 && (
        <p className={styles.cardText}>Запланированных встреч нет.</p>
      )}
      {items.length > 0 && (
        <ul className={styles.overviewList}>
          {items.map((a) => (
            <li key={a.uuid} className={styles.overviewItem}>
              <span className={styles.overviewMain}>{formatMoment(a.starts_at)}</span>
              <span className={styles.overviewMeta}>
                {a.meeting_type_name || 'Индивидуальная встреча'}
                {MEETING_STATUS[a.status] ? ` · ${MEETING_STATUS[a.status]}` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
      <Link to="/student/calendar" className={styles.cardAction}>
        Открыть календарь
      </Link>
    </section>
  );
}

function ActiveTasks({ disabled }) {
  const { items, hasMore, loading, error } = useOpenAssignmentsPreview({ enabled: !disabled });
  return (
    <section className={styles.actionCard} aria-labelledby="home-tasks-title">
      <h2 id="home-tasks-title" className={styles.cardTitle}>Активные задания</h2>
      {disabled && (
        <p className={styles.cardText}>Задания недоступны при входе под именем пользователя.</p>
      )}
      {!disabled && loading && <p className={styles.cardText}>Загружается…</p>}
      {!disabled && !loading && error && (
        <p className={styles.cardText}>Не удалось загрузить задания.</p>
      )}
      {!disabled && !loading && !error && items.length === 0 && (
        <p className={styles.cardText}>Активных заданий нет.</p>
      )}
      {items.length > 0 && (
        <ul className={styles.overviewList}>
          {items.map((t) => (
            <li key={t.uuid} className={styles.overviewItem}>
              <span className={`${styles.overviewMain} ${styles.overviewClamp}`}>{t.text}</span>
              {t.due_date && (
                <span className={styles.overviewMeta}>до {formatDueDate(t.due_date)}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {!disabled && (
        <Link to="/student/tasks" className={styles.cardAction}>
          {hasMore ? 'Все задания' : 'Открыть задания'}
        </Link>
      )}
    </section>
  );
}

function plural(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'запись';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'записи';
  return 'записей';
}

function getInsightText(count) {
  if (count <= 3) return 'Пока мало данных для тренда, но записи уже можно обсудить с психологом.';
  return 'Можно смотреть первые изменения.';
}

export default function StudentHome() {
  const { isImpersonating } = useAuth();
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
        });
      })
      .catch(() => {
        setObs14d({ entriesCount: 0, avgMood: null });
      });
  }, []);

  const todayLoading = todayEntry === undefined;
  const hasTodayEntry = todayEntry !== null && todayEntry !== undefined;

  return (
    <div className={styles.page}>
      <div className={styles.labelTag}>{todayLabel}</div>
      <h1 className={styles.pageTitle}>{NEUTRAL_GREETING}</h1>

      {/* ── Next step card ── */}
      <div className={styles.nextStepCard}>
        <div className={styles.nextStepContent}>
          <div className={styles.nextStepLabel}>Сегодня</div>
          {todayLoading ? (
            <>
              <h2 className={styles.nextStepTitle}>Ваш следующий шаг</h2>
              <p className={styles.nextStepText}>Загружается…</p>
            </>
          ) : hasTodayEntry ? (
            <>
              <h2 className={styles.nextStepTitle}>Сегодняшняя отметка сохранена</h2>
              <p className={styles.nextStepText}>
                Вы отметили состояние: {todayEntry.mood_score}/10. Можно добавить подробности или написать психологу.
              </p>
            </>
          ) : (
            <>
              <h2 className={styles.nextStepTitle}>Ваш следующий шаг</h2>
              <p className={styles.nextStepText}>
                Можно начать с короткой отметки самочувствия или перейти к материалам для самостоятельной работы.
              </p>
            </>
          )}
        </div>
        {!todayLoading && (
          <div className={styles.nextStepActions}>
            {hasTodayEntry ? (
              <>
                <Link to="/student/diary" className={styles.btnPrimary}>
                  Дополнить запись
                </Link>
                <Link to="/student/chat" className={styles.btnGhost}>
                  Написать психологу
                </Link>
              </>
            ) : (
              <>
                <Link to="/student/diary" className={styles.btnPrimary}>
                  Отметить состояние
                </Link>
                <Link to="/student/materials" className={styles.btnGhost}>
                  Открыть материалы
                </Link>
              </>
            )}
          </div>
        )}
      </div>

      {/* ── Встречи и задания ── */}
      <div className={styles.overviewGrid}>
        <UpcomingMeetings />
        <ActiveTasks disabled={Boolean(isImpersonating)} />
      </div>

      {/* ── Action cards ── */}
      <div className={styles.actionCardsGrid}>

        {/* Psychologist */}
        <div className={styles.actionCard}>
          <div className={styles.cardTitle}>Психолог</div>
          <p className={styles.cardText}>
            Связаться с психологом можно в чате.
          </p>
          <Link to="/student/chat" className={styles.cardAction}>
            Написать психологу
          </Link>
        </div>

        {/* Wellbeing */}
        <div className={styles.actionCard}>
          <div className={styles.cardTitle}>Самочувствие</div>
          {todayLoading ? (
            <p className={styles.cardText}>Загружается…</p>
          ) : hasTodayEntry ? (
            <>
              <p className={styles.cardMeta}>
                Сегодня: {todayEntry.mood_score}/10
                {MOOD_WORDS[todayEntry.mood_score]
                  ? ` · ${MOOD_WORDS[todayEntry.mood_score]}`
                  : ''}
              </p>
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
              <Link to="/student/diary" className={styles.cardAction}>
                Открыть дневник
              </Link>
            </>
          ) : (
            <>
              <p className={styles.cardText}>Сегодня ещё нет отметки.</p>
              <Link to="/student/diary" className={styles.cardAction}>
                Отметить
              </Link>
            </>
          )}
        </div>

        {/* Materials */}
        <div className={styles.actionCard}>
          <div className={styles.cardTitle}>Материалы</div>
          <p className={styles.cardText}>
            Статьи и упражнения для самостоятельной работы.
          </p>
          <Link to="/student/materials" className={styles.cardAction}>
            Открыть
          </Link>
        </div>
      </div>

      {/* ── Observation card (only when data exists) ── */}
      {obs14d !== null && obs14d.entriesCount > 0 && (
        <div className={styles.observationCard}>
          <div className={styles.obsHeader}>
            <span className={styles.obsTitle}>Самонаблюдение за 14 дней</span>
            <Link to="/student/diary" className={styles.obsLink}>
              Открыть дневник
            </Link>
          </div>
          <div className={styles.obsMeta}>
            <span className={styles.obsCount}>
              {obs14d.entriesCount} {plural(obs14d.entriesCount)}
            </span>
            {obs14d.avgMood !== null && (
              <span className={styles.obsAvg}>· среднее {obs14d.avgMood}/10</span>
            )}
          </div>
          <div className={styles.obsInsight}>{getInsightText(obs14d.entriesCount)}</div>
        </div>
      )}
    </div>
  );
}
