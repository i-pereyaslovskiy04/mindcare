import styles from './ProcessBlock.module.css';

const STEPS = [
  { title: 'Консультация', desc: 'Знакомство, определение вашего запроса и целей работы.' },
  { title: 'Анализ',       desc: 'Глубокое изучение ситуации и выявление ключевых причин.' },
  { title: 'Решения',      desc: 'Подбор индивидуальных инструментов и стратегий.' },
  { title: 'Поддержка',   desc: 'Сопровождение на пути к устойчивому результату.' },
];

export default function ProcessBlock() {
  return (
    <>
      <h2 className={styles.title}>Как проходит работа</h2>
      <div className={styles.timeline}>
        {STEPS.map((step, i) => (
          <div key={step.title} className={styles.step}>
            <div className={styles.stepHead}>
              <div className={styles.stepCircle}>
                {String(i + 1).padStart(2, '0')}
              </div>
              {i < STEPS.length - 1 && <div className={styles.stepLine} />}
            </div>
            <h3 className={styles.stepTitle}>{step.title}</h3>
            <p className={styles.stepDesc}>{step.desc}</p>
          </div>
        ))}
      </div>
    </>
  );
}
