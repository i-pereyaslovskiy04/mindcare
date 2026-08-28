import { useState } from 'react';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
// Баннер общий с главной (banner_slides CMS, placement='about') —
// не отдельная копия PageHero.
import Hero from '../home/components/Hero';
import AboutIntro from './components/AboutIntro';
import AboutMission from './components/AboutMission';
import AboutServicesPreview from './components/AboutServicesPreview';
import AboutApproach from './components/AboutApproach';
import AboutTrust from './components/AboutTrust';
import AboutMedia from './components/AboutMedia';

export default function About() {
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  return (
    <>
      <Navbar onOpenAuth={() => setIsAuthOpen(true)} />
      <Hero placement="about" />
      <AboutIntro />
      <AboutMission />
      <AboutServicesPreview />
      <AboutApproach />
      <AboutTrust />
      <AboutMedia />
      <Footer />
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </>
  );
}
