import styles from './StatCard.module.css';

export default function StatCard({ label, value, unit, trend, trendDown }) {
  return (
    <div className={styles.card}>
      <div className={styles.label}>{label}</div>
      <div className={styles.num}>
        {value}
        {unit && <em className={styles.unit}>{unit}</em>}
      </div>
      {trend && (
        <div className={trendDown ? styles.trendDown : styles.trend}>{trend}</div>
      )}
    </div>
  );
}
