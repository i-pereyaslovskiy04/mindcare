import styles from './CalendarDayCell.module.css';

const DOT_CLASS = {
  session: styles.dotSession,
  past:    styles.dotPast,
  task:    styles.dotTask,
  diary:   styles.dotDiary,
};

export default function CalendarDayCell({ cell, isToday, dotStatus, isSelected, events = [], onClick }) {
  const cls = [styles.cell];
  if (!cell.current) cls.push(styles.out);
  if (isToday && dotStatus !== 'upcoming') cls.push(styles.today);
  if (dotStatus === 'upcoming') cls.push(styles.sessionDay);
  if (isSelected) cls.push(styles.active);

  return (
    <div
      className={cls.join(' ')}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onClick?.(e)}
    >
      <span className={styles.num}>{cell.day}</span>
      {events.length > 0 && (
        <span className={styles.dots}>
          {events.slice(0, 4).map((type, i) => (
            <span key={i} className={`${styles.dot} ${DOT_CLASS[type] || ''}`} />
          ))}
        </span>
      )}
    </div>
  );
}
