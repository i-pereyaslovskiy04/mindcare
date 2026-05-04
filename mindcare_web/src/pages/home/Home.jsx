import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';
import { getRoleHome } from '../../features/auth/authUtils';
import Navbar from '../../components/Navbar/Navbar';
import Hero from './components/Hero';
import QuickActions from './components/QuickActions';
import NewsSection from '../../features/news/components/NewsSection';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
import CookieBanner from '../../components/CookieBanner/CookieBanner';

export default function Home() {
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const { user, loading, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const handleOpenAuth = () => setIsAuthModalOpen(true);
  const handleCloseAuth = () => setIsAuthModalOpen(false);
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
      <AuthModal isOpen={isAuthModalOpen} onClose={handleCloseAuth} />
      <CookieBanner />
    </>
  );
}
