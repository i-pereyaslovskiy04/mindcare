import { useState, useMemo } from 'react';
import { MOCK_SESSIONS } from './data/mockSessions';
import { MOCK_EVENTS } from './data/mockEvents';
import { dateKey } from './utils/calendarUtils';
import CalendarHeader from './components/CalendarHeader';
import CalendarGrid from './components/CalendarGrid';
import CalendarDayPopup from './components/CalendarDayPopup';
import UpcomingList from './components/UpcomingList';
import SessionHistory from './components/SessionHistory';
import styles from './CalendarPage.module.css';

const _today = new Date();
const todayKey = dateKey(_today.getFullYear(), _today.getMonth(), _today.getDate());

const FORMAT_OPTIONS = ['Видео', 'Аудио', 'Чат'];
const SLOT_OPTIONS = ['10:00', '11:30', '14:00', '15:30', '17:00'];

const LEGEND_ITEMS = [
  { label: 'Сессия',              color: 'var(--espresso)' },
  { label: 'Задание',             color: 'var(--coffee)'   },
  { label: 'Прошедшая встреча',   color: 'var(--latte)'    },
  { label: 'Запись в дневнике',   color: 'var(--success)'  },
];

export default function CalendarPage() {
  const [year, setYear] = useState(_today.getFullYear());
  const [month, setMonth] = useState(_today.getMonth());
  const [activeFormat, setActiveFormat] = useState('Видео');
  const [activeSlot, setActiveSlot] = useState(null);
  const [selectedDayKey, setSelectedDayKey] = useState(null);

  const sessionMap = useMemo(() => {
    const map = {};
    MOCK_SESSIONS.forEach(s => { map[s.date] = s; });
    return map;
  }, []);

  const eventsDetailMap = useMemo(() => {
    const map = {};
    MOCK_EVENTS.forEach(e => {
      if (!map[e.date]) map[e.date] = [];
      map[e.date].push(e);
    });
    return map;
  }, []);

  const upcoming = useMemo(
    () => MOCK_SESSIONS.filter(s => s.status === 'upcoming').sort((a, b) => a.date.localeCompare(b.date)),
    []
  );
  const past = useMemo(
    () => MOCK_SESSIONS.filter(s => s.status === 'past').sort((a, b) => a.date.localeCompare(b.date)),
    []
  );

  function prev() {
    if (month === 0) { setYear(y => y - 1); setMonth(11); }
    else setMonth(m => m - 1);
  }

  function next() {
    if (month === 11) { setYear(y => y + 1); setMonth(0); }
    else setMonth(m => m + 1);
  }

  return (
    <div className={styles.page}>
      <div className={styles.left}>
        <section className={styles.calendarBox}>
          <CalendarHeader year={year} month={month} onPrev={prev} onNext={next} />
          <CalendarGrid
            year={year}
            month={month}
            sessionMap={sessionMap}
            todayKey={todayKey}
            onDaySelect={setSelectedDayKey}
          />
          <div className={styles.legend}>
            {LEGEND_ITEMS.map(item => (
              <span key={item.label} className={styles.legendItem}>
                <span className={styles.legendDot} style={{ background: item.color }} />
                {item.label}
              </span>
            ))}
          </div>
        </section>

        {selectedDayKey && (
          <CalendarDayPopup
            events={eventsDetailMap[selectedDayKey] || []}
            onClose={() => setSelectedDayKey(null)}
          />
        )}

        <UpcomingList sessions={upcoming} />
        <SessionHistory sessions={past} />
      </div>

      <div className={styles.right}>
        <section className={styles.bookingBox}>
          <h3 className={styles.bookingTitle}>Записаться на сессию</h3>

          <div className={styles.field}>
            <label className={styles.fieldLabel}>Специалист</label>
            <select className={styles.select}>
              <option>Мария Ковалёва</option>
            </select>
          </div>

          <div className={styles.field}>
            <label className={styles.fieldLabel}>Формат</label>
            <div className={styles.chips}>
              {FORMAT_OPTIONS.map(f => (
                <button
                  key={f}
                  className={activeFormat === f ? `${styles.chip} ${styles.chipActive}` : styles.chip}
                  onClick={() => setActiveFormat(f)}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          <div className={styles.field}>
            <label className={styles.fieldLabel}>Доступные слоты</label>
            <div className={styles.slots}>
              {SLOT_OPTIONS.map(t => (
                <button
                  key={t}
                  className={activeSlot === t ? `${styles.slot} ${styles.slotActive}` : styles.slot}
                  onClick={() => setActiveSlot(prev => prev === t ? null : t)}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <button className={styles.bookBtn} disabled={!activeSlot}>Записаться</button>
        </section>
      </div>
    </div>
  );
}
