import { Link } from 'react-router-dom';
import styles from './NewsSection.module.css';
import { ArrowRightIcon } from '../icons';

// Placeholder image until real images are available.
const PlaceholderImage = () => (
  <svg width="60" height="60" viewBox="0 0 60 60" fill="none" aria-hidden="true">
    <circle cx="30" cy="22" r="12" stroke="#8B6F47" strokeWidth="1.5" fill="none" />
    <path d="M8 54c0-12.15 9.85-22 22-22s22 9.85 22 22" stroke="#8B6F47" strokeWidth="1.5" fill="none" />
  </svg>
);

export default function FeaturedNews({ news, className, style }) {
  return (
    <Link
      to={`/news/${news.id}`}
      className={`${styles.newsFeatured} ${className}`}
      style={style}
    >
      <div className={styles.newsImg}>
        <PlaceholderImage />
      </div>
      <div className={styles.newsBody}>
        <div className={styles.newsTag}>{news.tag}</div>
        <div className={styles.newsH}>{news.title}</div>
        <div className={styles.newsDesc}>{news.description}</div>
        <div className={styles.newsDate}>{news.date}</div>
        <div className={styles.newsReadMore} aria-hidden="true">
          Читать далее <ArrowRightIcon />
        </div>
      </div>
    </Link>
  );
}
