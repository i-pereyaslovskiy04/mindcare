import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
import { getNewsById } from '../../api/news.api';
import styles from './NewsItemPage.module.css';

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
    <circle cx="620" cy="120" r="4" fill="white" fillOpacity="0.12" />
    <circle cx="280" cy="350" r="3" fill="white" fillOpacity="0.10" />
    <circle cx="700" cy="340" r="5" fill="white" fillOpacity="0.08" />
    <circle cx="180" cy="150" r="3" fill="white" fillOpacity="0.09" />
  </svg>
);

const MOCK_PARAGRAPHS = [
  'Психологическая служба ДонГУ — это команда дипломированных специалистов, которые помогают студентам справляться с эмоциональными трудностями, адаптироваться к учебным нагрузкам и выстраивать здоровые межличностные отношения. Ежегодно сотни студентов обращаются за поддержкой и находят её именно здесь.',
  'На встрече будут представлены все форматы работы центра: очные консультации, групповые тренинги и онлайн-сессии. Специалисты расскажут о наиболее распространённых запросах — управлении тревогой, эмоциональном выгорании и прокрастинации — и объяснят, как центр может помочь в каждом конкретном случае.',
  'По итогам прошлого учебного года более 87% студентов, прошедших курс поддержки, отметили заметное улучшение общего самочувствия. Центр работает в партнёрстве с профильными кафедрами факультета психологии, что обеспечивает высокий профессиональный уровень и актуальность применяемых методик.',
  'Участие бесплатное и открыто для всех студентов, аспирантов и сотрудников университета. Для записи на индивидуальную консультацию используйте форму на сайте или свяжитесь с нами по электронной почте. Ждём вас.',
];

const MOCK_QUOTE =
  '«Обращаться за поддержкой — это не слабость, это осознанный выбор заботы о себе. Наша задача — сделать этот шаг максимально простым.»';

export default function NewsItemPage() {
  const { id } = useParams();
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [news, setNews] = useState(null);
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
                {news.tag && <span className={styles.tag}>{news.tag}</span>}
                <h1 className={styles.title}>{news.title}</h1>
                <div className={styles.meta}>
                  {news.date && <span>{news.date}</span>}
                  <span className={styles.metaDivider} aria-hidden="true">·</span>
                  <span>3 мин чтения</span>
                </div>
              </header>

              <div className={styles.heroWrap}>
                {news.image
                  ? <img src={news.image} alt={news.title} className={styles.heroImg} />
                  : <HeroPlaceholder />}
              </div>

              <div className={styles.body}>
                {news.content ? (
                  <p>{news.content}</p>
                ) : (
                  <>
                    <p className={styles.lead}>{news.description}</p>
                    <p>{MOCK_PARAGRAPHS[0]}</p>
                    <p>{MOCK_PARAGRAPHS[1]}</p>
                    <blockquote className={styles.pullQuote}>{MOCK_QUOTE}</blockquote>
                    <p>{MOCK_PARAGRAPHS[2]}</p>
                    <p>{MOCK_PARAGRAPHS[3]}</p>
                  </>
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
