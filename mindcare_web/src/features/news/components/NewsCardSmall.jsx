import { Link } from 'react-router-dom';
import styles from './NewsSection.module.css';

const ArticleIcon = () => (
  <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true" style={{ color: 'var(--coffee)' }}>
    <rect x="2" y="4" width="22" height="17" rx="3" stroke="currentColor" strokeWidth="1.3" fill="none" />
    <path d="M7 12h12M7 17h8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
  </svg>
);

const WebinarIcon = () => (
  <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true" style={{ color: 'var(--coffee)' }}>
    <circle cx="13" cy="13" r="10" stroke="currentColor" strokeWidth="1.3" fill="none" />
    <path d="M13 8v5l3.5 3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
  </svg>
);

const TAG_ICONS = { Статья: ArticleIcon };

// Small card: lightweight secondary layout.
// Image fills the card; gradient darkens the bottom; title + date sit directly on gradient.
// No glass panel, no blur, no tag, no read-more — keeps hierarchy clear vs. the featured card.
// To revert: restore tag div, read-more div, actionLabel, ArrowRightIcon import.
export default function NewsCardSmall({ news, className, style }) {
  const TagIcon = TAG_ICONS[news.tag] ?? WebinarIcon;

  return (
    <Link
      to={`/news/${news.id}`}
      className={`${styles.newsCardSmOverlay} ${className}`}
      style={style}
    >
      {news.image
        ? <img src={news.image} alt={news.title} className={styles.newsImgFullCover} />
        : <div className={styles.newsImgPlaceholderFull}><TagIcon /></div>}
      <div className={styles.newsBodySmOverlay}>
        <div className={`${styles.newsHOverlay} ${styles.newsHSmOverlay}`}>{news.title}</div>
        <div className={styles.newsDateOverlay}>{news.date}</div>
      </div>
    </Link>
  );
}
