import Icon from '../../../../components/Icon/Icon';
import { MONTH_NAMES_GENITIVE } from '../utils/calendarUtils';
import Button from '../../../../components/UI/Button/Button';
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
        {sessions.map((s, i) => {
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
              <div className={styles.right}>
                <span className={styles.badge}>Подтверждена</span>
                {i === 0 && (
                  <Button variant="primary" size="sm">Подключиться</Button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
