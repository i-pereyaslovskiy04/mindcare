import styles from './Hero.module.css';

export default function Hero() {
  return (
    <div className={styles.hero}>
      <div className={styles.heroInner}>
        <div className={styles.heroLabel}>Психологическая служба · ДонГУ</div>
        <h1 className={styles.heroTitle}>
          Забота о вашей<br />
          <span className={styles.heroTitleHighlight}>душевной гармонии</span>
        </h1>
        <p className={styles.heroSub}>
          Профессиональная психологическая поддержка студентов и сотрудников Донецкого государственного университета.
        </p>
      </div>
      <div className={styles.heroDots}>
        <span className={`${styles.heroDot} ${styles.active}`} aria-hidden="true" />
        <span className={styles.heroDot} aria-hidden="true" />
        <span className={styles.heroDot} aria-hidden="true" />
      </div>
    </div>
  );
}
