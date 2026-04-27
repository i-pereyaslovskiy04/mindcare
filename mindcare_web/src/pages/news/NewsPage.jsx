import { useState, useEffect } from 'react';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../components/AuthModal/AuthModal';
import NewsGrid from '../../components/NewsPage/NewsGrid';
import Pagination from '../../components/NewsPage/Pagination';
import { getNews } from '../../services/api';
import styles from '../../components/NewsPage/NewsPage.module.css';

const LIMIT = 9;

export default function NewsPage() {
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [news, setNews] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);

    getNews(page, LIMIT).then((data) => {
      const items = Array.isArray(data) ? data : (data.items || []);
      const total = data.total != null ? data.total : items.length;
      setNews(items);
      setTotalPages(Math.max(1, Math.ceil(total / LIMIT)));
      setLoading(false);
    });
  }, [page]);

  const handlePageChange = (p) => {
    setPage(p);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <>
      <Navbar onOpenAuth={() => setIsAuthOpen(true)} />

      <div className={styles.pageWrap}>
        <div className={`container ${styles.pageInner}`}>
          <header className={styles.pageHeader}>
            <h1 className={styles.pageTitle}>Новости и события</h1>
          </header>

          {loading && (
            <p className={styles.loading} aria-live="polite">
              Загружаем новости…
            </p>
          )}

          {!loading && (
            <>
              <NewsGrid items={news} />
              {totalPages > 1 && (
                <Pagination page={page} totalPages={totalPages} onPage={handlePageChange} />
              )}
            </>
          )}
        </div>
      </div>

      <Footer />
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </>
  );
}
