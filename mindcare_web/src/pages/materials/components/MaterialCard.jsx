import { Link } from 'react-router-dom';
import styles from './MaterialCard.module.css';

const TAG_CLASS = {
  Статья:     'tagArticle',
  Вебинар:    'tagWebinar',
  Упражнение: 'tagExercise',
  Гид:        'tagGuide',
};

const PlaceholderIcon = () => (
  <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
    <rect x="6" y="10" width="36" height="28" rx="4" stroke="#C9B99A" strokeWidth="1.5" fill="none" />
    <circle cx="17" cy="20" r="4" stroke="#C9B99A" strokeWidth="1.5" fill="none" />
    <path
      d="M6 32l10-8 8 8 6-5 12 9"
      stroke="#C9B99A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
    />
  </svg>
);

export default function MaterialCard({ item }) {
  const tagCls = TAG_CLASS[item.tag] ?? 'tagArticle';

  return (
    <article className={styles.card}>
      <div className={styles.imgWrap}>
        {item.image
          ? <img src={item.image} alt={item.title} className={styles.img} loading="lazy" />
          : <div className={styles.placeholder}><PlaceholderIcon /></div>
        }
      </div>

      <div className={styles.body}>
        <span className={`${styles.tag} ${styles[tagCls]}`}>{item.tag}</span>
        <h3 className={styles.title}>{item.title}</h3>
        <p className={styles.desc}>{item.description}</p>
        <time className={styles.date}>{item.date}</time>
        <Link to={`/materials/${item.id}`} className={styles.btn}>Подробнее</Link>
      </div>
    </article>
  );
}
