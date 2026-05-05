import Icon from '../../components/Icon';
import { MONTH_NAMES } from '../utils/calendarUtils';
import styles from './CalendarHeader.module.css';

export default function CalendarHeader({ year, month, onPrev, onNext }) {
  return (
    <div className={styles.header}>
      <div className={styles.titleBlock}>
        <span className={styles.monthLabel}>{MONTH_NAMES[month]}</span>
        <span className={styles.yearLabel}>{year}</span>
      </div>
      <div className={styles.nav}>
        <button className={styles.navBtn} onClick={onPrev} aria-label="Предыдущий месяц">
          <Icon name="chevron-left" size={16} />
        </button>
        <button className={styles.navBtn} onClick={onNext} aria-label="Следующий месяц">
          <Icon name="chevron-right" size={16} />
        </button>
      </div>
    </div>
  );
}
