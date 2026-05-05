import Icon from '../../components/Icon';
import styles from './TaskItem.module.css';

const BADGE = {
  done:     { label: 'Выполнено', cls: styles.badgeDone },
  urgent:   { label: 'Срочно',    cls: styles.badgeUrgent },
  progress: { label: 'В работе',  cls: styles.badgeProgress },
};

export default function TaskItem({ task, onToggle }) {
  const badge = task.done ? BADGE.done : task.urgent ? BADGE.urgent : BADGE.progress;

  return (
    <div className={`${styles.item} ${task.done ? styles.done : ''}`}>
      <button
        className={`${styles.checkbox} ${task.done ? styles.checkboxOn : ''}`}
        onClick={() => onToggle(task.id)}
        aria-label={task.done ? 'Снять отметку' : 'Отметить выполненным'}
      />

      <div className={styles.body}>
        <div className={styles.head}>
          <div className={styles.title}>{task.title}</div>
          <span className={`${styles.badge} ${badge.cls}`}>{badge.label}</span>
        </div>

        <p className={styles.desc}>{task.desc}</p>

        {task.comment && (
          <div className={styles.comment}>
            <b>Мария Ковалёва:</b> {task.comment}
          </div>
        )}

        <div className={styles.foot}>
          <span className={styles.footItem}>
            <Icon name="calendar" size={11} stroke={1.6} />
            {task.due}
          </span>
          <span className={styles.dot}>·</span>
          <span className={styles.footItem}>{task.tag}</span>
        </div>
      </div>
    </div>
  );
}
