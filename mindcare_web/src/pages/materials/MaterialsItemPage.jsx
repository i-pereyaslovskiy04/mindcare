import { Fragment, useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
import { getMaterialById } from '../../api/materials.api';
import styles from './MaterialsItemPage.module.css';

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

function readTime(item) {
  const words = [item.description, ...(item.body ?? [])].join(' ').trim().split(/\s+/).length;
  return `${Math.max(1, Math.ceil(words / 200))} мин чтения`;
}

export default function MaterialsItemPage() {
  const { id } = useParams();
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [item, setItem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    setLoading(true);
    setNotFound(false);
    getMaterialById(id)
      .then((data) => setItem(data))
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [id]);

  const quoteAfter = item?.body ? Math.floor(item.body.length * 0.6) - 1 : -1;

  return (
    <>
      <Navbar onOpenAuth={() => setIsAuthOpen(true)} />

      <div className={styles.pageWrap}>
        <div className={`container ${styles.pageInner}`}>
          <Link to="/materials" className={styles.backLink}>← Все материалы</Link>

          {loading && <p className={styles.stateText}>Загружаем…</p>}
          {!loading && notFound && <p className={styles.stateText}>Материал не найден.</p>}

          {!loading && item && (
            <article className={styles.article}>
              <header className={styles.header}>
                {item.tag && <span className={styles.tag}>{item.tag}</span>}
                <h1 className={styles.title}>{item.title}</h1>
                <div className={styles.meta}>
                  {item.date && <span>{item.date}</span>}
                  <span className={styles.metaDivider} aria-hidden="true">·</span>
                  <span>{readTime(item)}</span>
                </div>
              </header>

              <div className={styles.heroWrap}>
                {item.image
                  ? <img src={item.image} alt={item.title} className={styles.heroImg} />
                  : <HeroPlaceholder />
                }
              </div>

              <div className={styles.body}>
                <p className={styles.lead}>{item.description}</p>

                {item.body?.map((paragraph, i) => (
                  <Fragment key={i}>
                    <p>{paragraph}</p>
                    {item.quote && i === quoteAfter && (
                      <blockquote className={styles.pullQuote}>{item.quote}</blockquote>
                    )}
                  </Fragment>
                ))}
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
