import styles from './PageHero.module.css';

export default function PageHero({ eyebrow, title, sub }) {
  return (
    <section className={styles.hero}>
      <div className={styles.inner}>
        {eyebrow && <p className={styles.eyebrow}>{eyebrow}</p>}
        <h1 className={styles.title}>{title}</h1>
        {sub && <p className={styles.sub}>{sub}</p>}
      </div>
    </section>
  );
}
