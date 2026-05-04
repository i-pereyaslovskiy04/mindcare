import { useState } from 'react';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
import NewsGrid from './components/NewsGrid';
import Pagination from './components/Pagination';
import { useNews } from '../../hooks/useNews';
import styles from './components/NewsPage.module.css';

export default function NewsPage() {
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [page, setPage] = useState(1);

  const { items, totalPages, loading } = useNews(page);

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
              <NewsGrid items={items} />
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
