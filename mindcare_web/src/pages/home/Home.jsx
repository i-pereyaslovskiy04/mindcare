import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';
import { getRoleHome } from '../../shared/lib/routes';
import Navbar from '../../components/Navbar/Navbar';
import Hero from './components/Hero';
import QuickActions from './components/QuickActions';
import NewsSection from '../../features/news/components/NewsSection';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
import CookieBanner from '../../components/CookieBanner/CookieBanner';

export default function Home() {
  const location = useLocation();
  const { user, loading, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  // Router state set by password-change redirect or route guards
  const { openAuth, message: routerMessage } = location.state ?? {};

  const [isAuthModalOpen, setIsAuthModalOpen] = useState(openAuth === 'login');
  const [authMessage, setAuthMessage] = useState(routerMessage ?? '');

  // Clear router state so back-navigation doesn't re-trigger the modal
  useEffect(() => {
    if (openAuth) {
      window.history.replaceState({}, '');
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleOpenAuth = () => {
    if (isAuthenticated) return;
    setIsAuthModalOpen(true);
  };
  const handleCloseAuth = () => {
    setIsAuthModalOpen(false);
    setAuthMessage('');
  };
  const handleGoToDashboard = () => navigate(getRoleHome(user?.role));

  return (
    <>
      <Navbar onOpenAuth={handleOpenAuth} />
      <Hero />
      {!loading && isAuthenticated && (
        <QuickActions onGoToDashboard={handleGoToDashboard} />
      )}
      <NewsSection />
      <Footer />
      {!loading && !isAuthenticated && (
        <AuthModal isOpen={isAuthModalOpen} onClose={handleCloseAuth} message={authMessage} />
      )}
      <CookieBanner />
    </>
  );
}
