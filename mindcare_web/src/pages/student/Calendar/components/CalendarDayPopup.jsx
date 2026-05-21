import { useEffect, useRef } from 'react';
import styles from './CalendarDayPopup.module.css';

const TYPE_LABEL = {
  session: 'Сессия',
  past:    'Прошедшая встреча',
  task:    'Задание',
  diary:   'Запись в дневнике',
};

const TYPE_COLOR = {
  session: 'var(--espresso)',
  past:    'var(--latte)',
  task:    'var(--coffee)',
  diary:   'var(--success)',
};

export default function CalendarDayPopup({ events, onClose, top, left, arrowLeft }) {
  const ref = useRef(null);

  useEffect(() => {
    function handle(e) {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    }
    const id = setTimeout(() => document.addEventListener('click', handle), 0);
    return () => { clearTimeout(id); document.removeEventListener('click', handle); };
  }, [onClose]);

  if (!events.length) return null;

  return (
    <div
      ref={ref}
      className={styles.popup}
      style={{ top, left, '--arrow-left': `${arrowLeft ?? 140}px` }}
    >
      <div className={styles.header}>
        <span className={styles.heading}>События дня</span>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Закрыть">✕</button>
      </div>
      <ul className={styles.list}>
        {events.map((ev, i) => (
          <li key={i} className={styles.item}>
            <span className={styles.dot} style={{ background: TYPE_COLOR[ev.type] }} />
            <div className={styles.body}>
              <div className={styles.meta}>
                <span className={styles.typeLabel}>{TYPE_LABEL[ev.type] || ev.type}</span>
                {ev.time && <span className={styles.time}>{ev.time}</span>}
              </div>
              {ev.title && <span className={styles.title}>{ev.title}</span>}
              {ev.desc  && <span className={styles.desc}>{ev.desc}</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
