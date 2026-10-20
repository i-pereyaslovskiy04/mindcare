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

/**
 * Окно «События дня» (не модальное). Открывается для любого дня месяца:
 * без записей — «На этот день записей нет». id связывает его с кнопкой дня
 * (aria-controls). onClose({ restoreFocus }) — «✕» и Escape возвращают фокус
 * на кнопку дня, клик снаружи — нет.
 */
export default function CalendarDayPopup({ id, events, onClose, top, left, arrowLeft }) {
  const ref = useRef(null);

  useEffect(() => {
    function handle(e) {
      if (ref.current && !ref.current.contains(e.target)) onClose({ restoreFocus: false });
    }
    const timer = setTimeout(() => document.addEventListener('click', handle), 0);
    return () => { clearTimeout(timer); document.removeEventListener('click', handle); };
  }, [onClose]);

  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') onClose({ restoreFocus: true });
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      id={id}
      ref={ref}
      className={styles.popup}
      style={{ top, left, '--arrow-left': `${arrowLeft ?? 140}px` }}
    >
      <div className={styles.header}>
        <span className={styles.heading}>События дня</span>
        <button
          type="button"
          className={styles.closeBtn}
          onClick={() => onClose({ restoreFocus: true })}
          aria-label="Закрыть"
        >
          ✕
        </button>
      </div>
      {events.length === 0 ? (
        <p className={styles.empty}>На этот день записей нет</p>
      ) : (
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
      )}
    </div>
  );
}
