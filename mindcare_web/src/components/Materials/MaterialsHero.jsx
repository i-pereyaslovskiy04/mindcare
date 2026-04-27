import styles from './MaterialsHero.module.css';

export default function MaterialsHero() {
  return (
    <section className={styles.hero}>
      <div className={styles.inner}>
        <p className={styles.eyebrow}>Ресурсный центр практической психологии</p>
        <h1 className={styles.title}>Материалы</h1>
        <p className={styles.sub}>
          Статьи, вебинары и упражнения для поддержки психологического здоровья
        </p>
      </div>
    </section>
  );
}
