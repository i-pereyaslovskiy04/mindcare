import { MONTH_NAMES_GENITIVE } from '../utils/calendarUtils';
import styles from './SessionHistory.module.css';

function parseDate(dateStr) {
  const parts = dateStr.split('-').map(Number);
  return { day: parts[2], month: parts[1] - 1 };
}

export default function SessionHistory({ sessions }) {
  if (!sessions.length) return null;

  return (
    <section className={styles.section}>
      <h3 className={styles.heading}>История сессий</h3>
      <ul className={styles.list}>
        {[...sessions].reverse().map(s => {
          const { day, month } = parseDate(s.date);
          return (
            <li key={s.id} className={styles.item}>
              <div className={styles.dateCol}>
                <span className={styles.day}>{day}</span>
                <span className={styles.mon}>{MONTH_NAMES_GENITIVE[month]}</span>
              </div>
              <div className={styles.body}>
                <span className={styles.title}>{s.title}</span>
                {s.desc && <span className={styles.desc}>{s.desc}</span>}
                {s.psychologist && (
                  <span className={styles.psych}>{s.psychologist}</span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
