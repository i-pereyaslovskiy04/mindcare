import styles from './AboutHero.module.css';

export default function AboutHero() {
  return (
    <section className={styles.hero}>
      <div className={`container ${styles.inner}`}>
        <p className={styles.label}>Донецкий государственный университет</p>
        <h1 className={styles.title}>
          Ресурсный центр<br />практической психологии
        </h1>
        <p className={styles.sub}>
          Психологическая помощь и поддержка студентов,
          преподавателей и сотрудников ДонГУ
        </p>
      </div>
    </section>
  );
}
