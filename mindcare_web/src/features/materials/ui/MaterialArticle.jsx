import DOMPurify from 'dompurify';
import Tag from '../../../components/UI/Tag/Tag';
import { formatMaterialDate } from '../lib/normalizeArticle';
import styles from './MaterialArticle.module.css';

// Hex в градиентах ниже — осознанное исключение из токенов: декоративная
// SVG-заглушка обложки (stopColor не поддерживает var()), едина для всех тем.
const HeroPlaceholder = () => (
  <svg
    viewBox="0 0 900 460"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={styles.heroSvg}
    aria-hidden="true"
  >
    <defs>
      <linearGradient id="matBg" x1="0" y1="0" x2="900" y2="460" gradientUnits="userSpaceOnUse">
        <stop stopColor="#3B2314" />
        <stop offset="1" stopColor="#6B4226" />
      </linearGradient>
      <radialGradient id="matGlow" cx="450" cy="230" r="240" gradientUnits="userSpaceOnUse">
        <stop stopColor="#C49A6C" stopOpacity="0.25" />
        <stop offset="1" stopColor="#C49A6C" stopOpacity="0" />
      </radialGradient>
    </defs>
    <rect width="900" height="460" fill="url(#matBg)" />
    <ellipse cx="450" cy="230" rx="250" ry="240" fill="url(#matGlow)" />
    <circle cx="450" cy="230" r="190" stroke="white" strokeOpacity="0.04" />
    <circle cx="450" cy="230" r="130" stroke="white" strokeOpacity="0.07" />
    <circle cx="450" cy="230" r="70"  stroke="white" strokeOpacity="0.10" />
    <rect x="418" y="194" width="64" height="76" rx="5"
      stroke="white" strokeOpacity="0.55" strokeWidth="1.5" fill="none" />
    <line x1="430" y1="214" x2="470" y2="214"
      stroke="white" strokeOpacity="0.38" strokeWidth="1.5" strokeLinecap="round" />
    <line x1="430" y1="227" x2="470" y2="227"
      stroke="white" strokeOpacity="0.38" strokeWidth="1.5" strokeLinecap="round" />
    <line x1="430" y1="240" x2="454" y2="240"
      stroke="white" strokeOpacity="0.38" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="620" cy="118" r="4" fill="white" fillOpacity="0.10" />
    <circle cx="280" cy="348" r="3" fill="white" fillOpacity="0.09" />
    <circle cx="700" cy="338" r="5" fill="white" fillOpacity="0.07" />
    <circle cx="182" cy="152" r="3" fill="white" fillOpacity="0.08" />
  </svg>
);

/**
 * Тело опубликованного материала: категория, заголовок, дата/автор, обложка,
 * лид, темы и HTML-содержимое. HTML проходит DOMPurify.sanitize — тот же
 * вызов, что и на публичной странице до выноса компонента.
 * fullBleed — обложка во всю ширину на узких экранах (только публичный сайт).
 */
export default function MaterialArticle({ item, fullBleed = false }) {
  const categoryLabel = item?.categories?.[0]?.name || null;
  const topics        = (item?.tags || []).map(t => t.name).filter(Boolean);
  const dateIso       = item?.published_at || item?.created_at || null;
  const dateLabel     = formatMaterialDate(dateIso);

  return (
    <article className={fullBleed ? `${styles.article} ${styles.bleed}` : styles.article}>
      <header className={styles.header}>
        {categoryLabel && <Tag variant="public" className={styles.tagItem}>{categoryLabel}</Tag>}
        <h1 className={styles.title}>{item.title}</h1>
        <div className={styles.meta}>
          {dateLabel && <time dateTime={dateIso}>{dateLabel}</time>}
          {item.created_by_name && (
            <>
              {dateLabel && <span className={styles.metaDivider} aria-hidden="true">·</span>}
              <span>{item.created_by_name}</span>
            </>
          )}
        </div>
        {topics.length > 0 && (
          <ul className={styles.topics} aria-label="Темы">
            {topics.map(name => <li key={name} className={styles.topic}>{name}</li>)}
          </ul>
        )}
      </header>

      <div className={styles.heroWrap}>
        {item.cover_image_url
          ? <img src={item.cover_image_url} alt="" className={styles.heroImg} />
          : <HeroPlaceholder />
        }
      </div>

      <div className={styles.body}>
        {item.excerpt && (
          <p className={styles.lead}>{item.excerpt}</p>
        )}
        {item.content ? (
          <div
            className={styles.richContent}
            dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(item.content) }}
          />
        ) : (
          !item.excerpt && <p className={styles.lead}>Содержимое материала не добавлено.</p>
        )}
      </div>
    </article>
  );
}
