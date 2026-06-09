import styles from './Badge.module.css';

const TONE_CLASS = {
  success:            styles.success,
  warning:            styles.warning,
  error:              styles.error,
  neutral:            styles.neutral,
  'role-student':     styles.roleStudent,
  'role-psychologist':styles.rolePsychologist,
  'role-admin':       styles.roleAdmin,
  'role-supervisor':  styles.roleSupervisor,
};

export default function Badge({ tone = 'neutral', className, children }) {
  const cls = [styles.badge, TONE_CLASS[tone] ?? styles.neutral, className]
    .filter(Boolean)
    .join(' ');

  return <span className={cls}>{children}</span>;
}
