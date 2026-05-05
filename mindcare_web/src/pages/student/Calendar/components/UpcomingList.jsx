import Icon from '../../components/Icon';
import { MONTH_NAMES_GENITIVE } from '../utils/calendarUtils';
import styles from './UpcomingList.module.css';

function parseDate(dateStr) {
  const parts = dateStr.split('-').map(Number);
  return { day: parts[2], month: parts[1] - 1 };
}

const TYPE_ICON = { audio: 'bell', chat: 'chat' };

export default function UpcomingList({ sessions }) {
  if (!sessions.length) return null;

  return (
    <section className={styles.section}>
      <h3 className={styles.heading}>Предстоящие сессии</h3>
      <ul className={styles.list}>
        {sessions.map(s => {
          const { day, month } = parseDate(s.date);
          const iconName = TYPE_ICON[s.type] || 'video';
          return (
            <li key={s.id} className={styles.item}>
              <div className={styles.iconBox}>
                <Icon name={iconName} size={18} />
              </div>
              <div className={styles.info}>
                <span className={styles.title}>{s.title}</span>
                <span className={styles.sub}>
                  {day} {MONTH_NAMES_GENITIVE[month]} · {s.time} · {s.psychologist}
                </span>
              </div>
              <span className={styles.badge}>Предстоит</span>
              <button className={styles.joinBtn}>Войти</button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
