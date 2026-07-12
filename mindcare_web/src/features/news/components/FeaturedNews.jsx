import { Link } from 'react-router-dom';
import styles from './NewsSection.module.css';
import { ArrowRightIcon } from '../../../components/icons';

const PlaceholderImage = () => (
  <svg width="60" height="60" viewBox="0 0 60 60" fill="none" aria-hidden="true" style={{ color: 'var(--coffee)' }}>
    <circle cx="30" cy="22" r="12" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <path d="M8 54c0-12.15 9.85-22 22-22s22 9.85 22 22" stroke="currentColor" strokeWidth="1.5" fill="none" />
  </svg>
);

// Overlay variant: image fills the full card, text sits on a warm gradient.
// To revert: change newsFeaturedOverlay → newsFeatured and overlay body/text
// classes back to newsImg + newsBody + newsTag + newsH + newsDesc + newsDate + newsReadMore.
export default function FeaturedNews({ news, className, style, compact }) {
  return (
    <Link
      to={`/news/${news.id}`}
      className={`${styles.newsFeaturedOverlay}${compact ? ` ${styles.newsFeaturedCompact}` : ''} ${className}`}
      style={style}
    >
      {news.image
        ? <img src={news.image} alt={news.title} className={styles.newsImgFullCover} />
        : <div className={styles.newsImgPlaceholderFull}><PlaceholderImage /></div>}
      <div className={styles.newsBodyOverlay}>
        <div className={styles.newsTagOverlay}>{news.tag}</div>
        <div className={styles.newsHOverlay}>{news.title}</div>
        <div className={styles.newsDescOverlay}>{news.description}</div>
        <div className={styles.newsDateOverlay}>{news.date}</div>
        <div className={styles.newsReadMoreOverlay} aria-hidden="true">
          Читать далее <ArrowRightIcon />
        </div>
      </div>
    </Link>
  );
}
