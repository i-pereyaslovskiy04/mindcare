import styles from './AboutMission.module.css';

const PILLARS = [
  { title: 'Здоровье',    desc: 'Психологически здоровая среда в университете' },
  { title: 'Развитие',    desc: 'Личностный и профессиональный рост каждого' },
  { title: 'Устойчивость', desc: 'Внутренний баланс и самореализация' },
];

export default function AboutMission() {
  return (
    <section className="section-wrap alt">
      <div className="container">
        <div className={styles.head}>
          <h2 className={styles.title}>Наша миссия</h2>
          <p className={styles.sub}>
            Поддержка, развитие и самореализация каждого человека —
            на каждом этапе университетского пути.
          </p>
        </div>
        <div className={styles.pillars}>
          {PILLARS.map((p) => (
            <div key={p.title} className={styles.pillar}>
              <h3 className={styles.pillarTitle}>{p.title}</h3>
              <p className={styles.pillarDesc}>{p.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
