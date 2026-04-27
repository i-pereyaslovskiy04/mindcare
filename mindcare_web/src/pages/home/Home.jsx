import { useState } from 'react';
import Navbar from '../../components/Navbar/Navbar';
import Hero from './components/Hero';
import QuickActions from './components/QuickActions';
import NewsSection from '../../components/News/NewsSection';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../components/AuthModal/AuthModal';
import CookieBanner from '../../components/CookieBanner/CookieBanner';

export default function Home() {
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  const handleOpenAuth = () => {
    setIsAuthModalOpen(true);
  };

  const handleCloseAuth = () => {
    setIsAuthModalOpen(false);
  };

  return (
    <>
      <Navbar onOpenAuth={handleOpenAuth} />
      <Hero />
      <QuickActions onOpenAuth={handleOpenAuth} />
      <NewsSection />
      <Footer />
      <AuthModal isOpen={isAuthModalOpen} onClose={handleCloseAuth} />
      <CookieBanner />
    </>
  );
}
