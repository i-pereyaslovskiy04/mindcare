import { useState } from 'react';
import { Link } from 'react-router-dom';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
import { usePageTitle } from '../../hooks/usePageTitle';
import styles from './NotFound.module.css';

export default function NotFound() {
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  usePageTitle('Страница не найдена');

  return (
    <>
      <Navbar onOpenAuth={() => setIsAuthOpen(true)} />
      <main id="main-content" className={styles.wrap}>
        <p className={styles.code}>404</p>
        <h1 className={styles.title}>Страница не найдена</h1>
        <p className={styles.sub}>Возможно, адрес изменился или страница была удалена.</p>
        <Link to="/" className={styles.link}>Вернуться на главную</Link>
      </main>
      <Footer />
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </>
  );
}
