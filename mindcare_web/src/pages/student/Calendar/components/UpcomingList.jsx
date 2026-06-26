import Icon from '../../../../components/Icon/Icon';
import { MONTH_NAMES_GENITIVE } from '../utils/calendarUtils';
import Badge from '../../../../components/UI/Badge/Badge';
import Button from '../../../../components/UI/Button/Button';
import styles from './UpcomingList.module.css';

function parseDate(dateStr) {
  const parts = dateStr.split('-').map(Number);
  return { day: parts[2], month: parts[1] - 1 };
}

const TYPE_ICON = { audio: 'bell', chat: 'chat' };

export default function UpcomingList({ sessions, onCancel }) {
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
                  {day} {MONTH_NAMES_GENITIVE[month]} · {s.time}
                  {s.psychologist ? ` · ${s.psychologist}` : ''}
                </span>
              </div>
              <div className={styles.right}>
                <Badge tone={s.statusTone || 'neutral'}>{s.statusLabel || 'Запись'}</Badge>
                {i === 0 && s.rawStatus === 'confirmed' && (
                  <Button variant="primary" size="sm" disabled>Подключиться</Button>
                )}
                {s.canCancel && onCancel && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => onCancel(s.uuid)}
                  >
                    Отменить
                  </Button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
