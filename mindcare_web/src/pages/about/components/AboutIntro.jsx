import styles from './AboutIntro.module.css';

const FACTS = [
  { value: '2022', label: 'Год основания' },
  { value: '5+',   label: 'Направлений работы' },
  { value: '100%', label: 'Профильное образование' },
];

export default function AboutIntro() {
  return (
    <section className="section-wrap">
      <div className={`container ${styles.grid}`}>
        <div className={styles.text}>
          <h2 className={styles.title}>О центре</h2>
          <p className={styles.body}>
            Центр практической психологии ДонГУ основан в 2022 году на базе кафедры
            психологии. Объединяем специалистов в области клинической, семейной и
            подростковой психологии.
          </p>
          <p className={styles.body}>
            Наша задача — помочь справиться с трудностями, восстановить внутренний
            баланс и улучшить качество жизни.
          </p>
        </div>
        <div className={styles.facts}>
          {FACTS.map((f) => (
            <div key={f.label} className={styles.fact}>
              <span className={styles.factValue}>{f.value}</span>
              <span className={styles.factLabel}>{f.label}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
