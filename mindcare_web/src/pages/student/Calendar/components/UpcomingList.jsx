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

/**
 * Карточка встречи: сверху — что/когда/с кем; нижняя строка — статус слева
 * (состояние, часть информации о встрече) и действия справа, отдельной
 * группой. На узкой карточке действия переносятся под статус.
 */
export default function UpcomingList({ sessions, onCancel }) {
  if (!sessions.length) return null;

  return (
    <section className={styles.section}>
      <h3 className={styles.heading}>Предстоящие сессии</h3>
      <ul className={styles.list}>
        {sessions.map((s, i) => {
          const { day, month } = parseDate(s.date);
          const iconName = TYPE_ICON[s.type] || 'video';
          const canJoin = i === 0 && s.rawStatus === 'confirmed';
          const canCancel = s.canCancel && onCancel;
          return (
            <li key={s.id} className={styles.item}>
              <div className={styles.iconBox}>
                <Icon name={iconName} size={18} />
              </div>
              <div className={styles.body}>
                <div className={styles.info}>
                  <span className={styles.title}>{s.title}</span>
                  <span className={styles.sub}>
                    {day} {MONTH_NAMES_GENITIVE[month]} · {s.time}
                    {s.psychologist ? ` · ${s.psychologist}` : ''}
                  </span>
                </div>
                <div className={styles.footer}>
                  <Badge tone={s.statusTone || 'neutral'}>{s.statusLabel || 'Запись'}</Badge>
                  {(canJoin || canCancel) && (
                    <div className={styles.actions}>
                      {canJoin && (
                        <Button variant="primary" size="sm" disabled>Подключиться</Button>
                      )}
                      {canCancel && (
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
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
