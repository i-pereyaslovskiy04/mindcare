import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import DOMPurify from 'dompurify';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
import { getNewsById } from '../../api/news.api';
import Tag from '../../components/UI/Tag/Tag';
import styles from './NewsItemPage.module.css';

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

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
      <linearGradient id="heroBg" x1="0" y1="0" x2="900" y2="460" gradientUnits="userSpaceOnUse">
        <stop stopColor="#2A1A10" />
        <stop offset="1" stopColor="#7A5535" />
      </linearGradient>
      <radialGradient id="heroGlow" cx="450" cy="230" r="240" gradientUnits="userSpaceOnUse">
        <stop stopColor="#C49A6C" stopOpacity="0.28" />
        <stop offset="1" stopColor="#C49A6C" stopOpacity="0" />
      </radialGradient>
    </defs>
    <rect width="900" height="460" fill="url(#heroBg)" />
    <ellipse cx="450" cy="230" rx="250" ry="250" fill="url(#heroGlow)" />
    <circle cx="450" cy="230" r="190" stroke="white" strokeOpacity="0.04" />
    <circle cx="450" cy="230" r="130" stroke="white" strokeOpacity="0.07" />
    <circle cx="450" cy="230" r="70"  stroke="white" strokeOpacity="0.10" />
    <circle cx="450" cy="207" r="28"  stroke="white" strokeOpacity="0.60" strokeWidth="1.5" />
    <path
      d="M406 278 C406 253 426 234 450 234 C474 234 494 253 494 278"
      stroke="white" strokeOpacity="0.60" strokeWidth="1.5" strokeLinecap="round"
    />
  </svg>
);

export default function NewsItemPage() {
  const { id } = useParams();
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [news, setNews]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    setLoading(true);
    setNotFound(false);
    getNewsById(id)
      .then((data) => setNews(data))
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [id]);

  const dateLabel = formatDate(news?.published_at || news?.created_at);

  return (
    <>
      <Navbar onOpenAuth={() => setIsAuthOpen(true)} />

      <div className={styles.pageWrap}>
        <div className={`container ${styles.pageInner}`}>
          <Link to="/news" className={styles.backLink}>← Все новости</Link>

          {loading && <p className={styles.stateText}>Загружаем…</p>}
          {!loading && notFound && <p className={styles.stateText}>Новость не найдена.</p>}

          {!loading && news && (
            <article className={styles.article}>
              <header className={styles.header}>
                {news.tags?.length > 0 && (
                  <div className={styles.tags}>
                    {news.tags.map(t => (
                      <Tag key={t.uuid} variant="public">{t.name}</Tag>
                    ))}
                  </div>
                )}
                <h1 className={styles.title}>{news.title}</h1>
                <div className={styles.meta}>
                  {dateLabel && <span>{dateLabel}</span>}
                  {news.created_by_name && (
                    <>
                      <span className={styles.metaDivider} aria-hidden="true">·</span>
                      <span>{news.created_by_name}</span>
                    </>
                  )}
                </div>
              </header>

              <div className={styles.heroWrap}>
                {news.cover_image_url
                  ? <img src={news.cover_image_url} alt={news.title} className={styles.heroImg} />
                  : <HeroPlaceholder />}
              </div>

              <div className={styles.body}>
                {news.content ? (
                  <div
                    className={styles.richContent}
                    dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(news.content) }}
                  />
                ) : (
                  <p className={styles.lead}>Содержимое новости не добавлено.</p>
                )}
              </div>
            </article>
          )}
        </div>
      </div>

      <Footer />
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </>
  );
}
