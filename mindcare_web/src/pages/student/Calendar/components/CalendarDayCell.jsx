import { dateKey, dayLabel } from '../utils/calendarUtils';
import styles from './CalendarDayCell.module.css';

const DOT_CLASS = {
  session: styles.dotSession,
  past:    styles.dotPast,
  task:    styles.dotTask,
  diary:   styles.dotDiary,
};

/**
 * Ячейка дня. Каждый день отображаемого месяца — настоящая
 * <button type="button"> (Enter/Space нативно): нажатие выбирает дату
 * (в т.ч. для формы записи) и открывает окно «События дня»
 * (aria-expanded/aria-controls). Дни соседнего месяца — текст без фокуса,
 * к ним переходят кнопками месяцев.
 *
 * Состояния не исключают друг друга: сегодня + сессия + выбран + соседний
 * месяц комбинируются классами; сегодня дополнительно — aria-current="date".
 */
export default function CalendarDayCell({
  cell,
  isToday,
  dotStatus,
  isSelected,
  isOpen,
  events = [],
  popupId,
  onClick,
}) {
  const interactive = cell.current;
  const cls = [styles.cell];
  if (interactive) cls.push(styles.interactive);
  if (!cell.current) cls.push(styles.out);
  if (isToday) cls.push(styles.today);
  if (dotStatus === 'upcoming') cls.push(styles.sessionDay);
  if (isSelected) cls.push(styles.active);
  const className = cls.join(' ');

  const content = (
    <>
      <span className={styles.num}>{cell.day}</span>
      {events.length > 0 && (
        <span className={styles.dots} aria-hidden="true">
          {events.slice(0, 4).map((type, i) => (
            <span key={i} className={`${styles.dot} ${DOT_CLASS[type] || ''}`} />
          ))}
        </span>
      )}
    </>
  );

  if (!interactive) {
    return (
      <div className={className} aria-current={isToday ? 'date' : undefined}>
        {content}
      </div>
    );
  }

  return (
    <button
      type="button"
      className={className}
      data-date={dateKey(cell.year, cell.month, cell.day)}
      aria-label={dayLabel(cell.year, cell.month, cell.day, {
        hasEvents: events.length > 0,
        selected: isSelected,
      })}
      aria-current={isToday ? 'date' : undefined}
      aria-expanded={isOpen}
      aria-controls={isOpen ? popupId : undefined}
      onClick={onClick}
    >
      {content}
    </button>
  );
}
