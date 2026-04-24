import styles from './NewsSection.module.css';
import { ArrowRightIcon } from '../icons';

const ArticleIcon = () => (
  <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true">
    <rect x="2" y="4" width="22" height="17" rx="3" stroke="#8B6F47" strokeWidth="1.3" fill="none" />
    <path d="M7 12h12M7 17h8" stroke="#8B6F47" strokeWidth="1.3" strokeLinecap="round" />
  </svg>
);

const WebinarIcon = () => (
  <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true">
    <circle cx="13" cy="13" r="10" stroke="#8B6F47" strokeWidth="1.3" fill="none" />
    <path d="M13 8v5l3.5 3.5" stroke="#8B6F47" strokeWidth="1.3" strokeLinecap="round" />
  </svg>
);

const TAG_ICONS = {
  Статья: ArticleIcon,
};

export default function NewsCardSmall({ news, className, style }) {
  const TagIcon = TAG_ICONS[news.tag] ?? WebinarIcon;
  const actionLabel = news.tag === 'Вебинар' ? 'Смотреть' : 'Читать';

  return (
    <a
      href={news.href}
      className={`${styles.newsCardSm} ${className}`}
      style={style}
    >
      <div className={styles.newsImgSm}>
        <TagIcon />
      </div>
      <div className={styles.newsBodySm}>
        <div className={styles.newsTag}>{news.tag}</div>
        <div className={`${styles.newsH} ${styles.newsHSm}`}>{news.title}</div>
        <div className={styles.newsDate}>{news.date}</div>
        <div
          className={`${styles.newsReadMore} ${styles.newsReadMoreSm}`}
          aria-hidden="true"
        >
          {actionLabel} <ArrowRightIcon width={11} height={11} strokeWidth={1.3} />
        </div>
      </div>
    </a>
  );
}
