import styles from './ServicesHero.module.css';

export default function ServicesHero() {
  return (
    <section className={styles.hero}>
      <div className={`container ${styles.heroInner}`}>
        <p className={styles.eyebrow}>Донецкий государственный университет</p>
        <h1 className={styles.title}>
          Центр психологической<br />помощи ДонГУ
        </h1>
        <p className={styles.sub}>
          Поддержка, развитие и психологическое благополучие студентов и сотрудников университета.
          Мы помогаем справляться с трудностями и находить внутренние ресурсы.
        </p>
      </div>
    </section>
  );
}
