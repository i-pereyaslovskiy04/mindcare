import styles from './AboutMedia.module.css';

const PlayIcon = () => (
  <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
    <circle cx="20" cy="20" r="18" stroke="currentColor" strokeWidth="1.5" opacity="0.4" />
    <path d="M16 13l13 7-13 7V13z" fill="currentColor" opacity="0.5" />
  </svg>
);

const ImageIcon = () => (
  <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true">
    <rect x="2" y="2" width="22" height="22" rx="4" stroke="currentColor" strokeWidth="1.5" opacity="0.4" />
    <circle cx="8.5" cy="8.5" r="2" fill="currentColor" opacity="0.4" />
    <path d="M2 17l6-5 4 4 3-3 9 7" stroke="currentColor" strokeWidth="1.5" opacity="0.4" strokeLinejoin="round" />
  </svg>
);

export default function AboutMedia() {
  return (
    <section className="section-wrap alt">
      <div className="container">
        <div className={styles.head}>
          <h2 className={styles.title}>Пространство центра</h2>
          <p className={styles.sub}>Комфортная и безопасная среда для работы и развития</p>
        </div>
        <div className={styles.grid}>
          <div className={`${styles.item} ${styles.video}`}>
            <div className={styles.placeholder}>
              <PlayIcon />
              <span>Видео о центре</span>
            </div>
          </div>
          {['Кабинет', 'Группа', 'Пространство'].map((label) => (
            <div key={label} className={styles.item}>
              <div className={styles.placeholder}>
                <ImageIcon />
                <span>{label}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
