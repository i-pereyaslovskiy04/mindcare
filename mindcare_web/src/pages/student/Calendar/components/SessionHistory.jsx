import { useId, useState } from 'react';
import Icon from '../../../../components/Icon/Icon';
import { MONTH_NAMES_GENITIVE } from '../utils/calendarUtils';
import Badge from '../../../../components/UI/Badge/Badge';
import styles from './SessionHistory.module.css';

function parseDate(dateStr) {
  const parts = dateStr.split('-').map(Number);
  return { day: parts[2], month: parts[1] - 1 };
}

/**
 * Итог встречи для истории — не статус записи. По контракту backend
 * (Appointment): completed — проведена, cancelled — отменена, declined —
 * отклонена психологом, no_show — студент не явился. `confirmed` в истории
 * оказывается только по времени: backend индивидуальные записи в completed
 * не переводит, поэтому итог неизвестен и не показывается (не «Состоялась»
 * и не «Подтверждена»).
 */
const OUTCOME = {
  completed: { label: 'Состоялась', tone: 'success' },
  cancelled: { label: 'Отменена',   tone: 'neutral' },
  declined:  { label: 'Отклонена',  tone: 'neutral' },
  no_show:   { label: 'Неявка',     tone: 'neutral' },
};

// Несостоявшиеся записи остаются в истории, но визуально вторичны.
const NOT_HELD = new Set(['cancelled', 'declined', 'no_show']);

/**
 * «История сессий» — компактный read-only журнал, по умолчанию свёрнут
 * (без сохранения состояния). Заголовок — <button> с aria-expanded /
 * aria-controls; количество записей видно без раскрытия.
 */
export default function SessionHistory({ sessions }) {
  const [open, setOpen] = useState(false);
  const listId = useId();

  if (!sessions.length) return null;

  return (
    <section className={styles.section}>
      <h3 className={styles.heading}>
        <button
          type="button"
          className={styles.toggle}
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen(o => !o)}
        >
          <span>История сессий</span>
          <span className={styles.count}>· {sessions.length}</span>
          <span className={open ? `${styles.chevron} ${styles.chevronOpen}` : styles.chevron} aria-hidden="true">
            <Icon name="chevron-right" size={16} />
          </span>
        </button>
      </h3>
      <ul id={listId} className={styles.list} hidden={!open}>
        {sessions.map(s => {
          const { day, month } = parseDate(s.date);
          const outcome = OUTCOME[s.rawStatus];
          return (
            <li
              key={s.id}
              className={NOT_HELD.has(s.rawStatus) ? `${styles.item} ${styles.notHeld}` : styles.item}
            >
              <span className={styles.date}>
                {day} {MONTH_NAMES_GENITIVE[month]}
              </span>
              <span className={styles.title}>{s.title}</span>
              {s.psychologist && (
                <span className={styles.psych}>{s.psychologist}</span>
              )}
              {s.desc && <span className={styles.desc}>{s.desc}</span>}
              {outcome && (
                <span className={styles.outcome}>
                  <Badge tone={outcome.tone}>{outcome.label}</Badge>
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
