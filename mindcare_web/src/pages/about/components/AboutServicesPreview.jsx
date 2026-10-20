import { Link } from 'react-router-dom';
import styles from './AboutServicesPreview.module.css';

const ITEMS = [
  { title: 'Консультирование', desc: 'Индивидуальная работа с психологом по личным и учебным вопросам.' },
  { title: 'Психодиагностика', desc: 'Современные методы оценки психологического состояния.' },
  { title: 'Тренинги',         desc: 'Навыки общения, саморегуляции и личностного роста.' },
  { title: 'Профориентация',   desc: 'Помощь в выборе профессионального пути и карьеры.' },
];

export default function AboutServicesPreview() {
  return (
    <section className="section-wrap">
      <div className="container">
        <div className={styles.head}>
          <h2 className={styles.title}>Направления работы</h2>
          <Link to="/services" className={styles.link}>Все услуги →</Link>
        </div>
        <div className={styles.grid}>
          {ITEMS.map((item, i) => (
            <div key={item.title} className={styles.card}>
              <span className={styles.num}>{String(i + 1).padStart(2, '0')}</span>
              <h3 className={styles.cardTitle}>{item.title}</h3>
              <p className={styles.cardDesc}>{item.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
