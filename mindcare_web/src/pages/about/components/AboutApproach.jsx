import styles from './AboutApproach.module.css';

const STEPS = [
  { num: '01', text: 'Первичная оценка запроса' },
  { num: '02', text: 'Подбор специалиста под задачу' },
  { num: '03', text: 'Работа с использованием современных методов' },
  { num: '04', text: 'Регулярное обновление подходов и методик' },
];

export default function AboutApproach() {
  return (
    <section className="section-wrap alt">
      <div className={`container ${styles.grid}`}>
        <div>
          <h2 className={styles.title}>Наш подход</h2>
          <p className={styles.body}>
            Работаем комплексно и бережно. Каждый запрос проходит первичную оценку,
            после чего подбирается наиболее подходящий специалист.
          </p>
        </div>
        <ol className={styles.steps}>
          {STEPS.map((s) => (
            <li key={s.num} className={styles.step}>
              <span className={styles.stepNum}>{s.num}</span>
              <span className={styles.stepText}>{s.text}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
