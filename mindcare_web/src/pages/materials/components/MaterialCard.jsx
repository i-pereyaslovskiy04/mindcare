import { Link } from 'react-router-dom';
import Tag from '../../../components/UI/Tag/Tag';
import styles from './MaterialCard.module.css';

const PlaceholderIcon = () => (
  <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true" style={{ color: 'var(--latte)' }}>
    <rect x="6" y="10" width="36" height="28" rx="4" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <circle cx="17" cy="20" r="4" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <path
      d="M6 32l10-8 8 8 6-5 12 9"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
    />
  </svg>
);

export default function MaterialCard({ item }) {
  return (
    <article className={styles.card}>
      <div className={styles.imgWrap}>
        {item.image
          ? <img src={item.image} alt={item.title} className={styles.img} loading="lazy" />
          : <div className={styles.placeholder}><PlaceholderIcon /></div>
        }
      </div>

      <div className={styles.body}>
        <Tag variant="card">{item.topic}</Tag>
        <h3 className={styles.title}>{item.title}</h3>
        <p className={styles.desc}>{item.description}</p>
        <time className={styles.date}>{item.date}</time>
        <Link to={`/materials/${item.id}`} className={styles.btn}>Подробнее</Link>
      </div>
    </article>
  );
}
