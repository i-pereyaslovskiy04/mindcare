import { useState } from 'react';
import Navbar from '../components/Navbar/Navbar';
import Footer from '../components/Footer/Footer';
import AuthModal from '../components/AuthModal/AuthModal';
import AboutHero from '../components/About/AboutHero';
import AboutIntro from '../components/About/AboutIntro';
import AboutMission from '../components/About/AboutMission';
import AboutServicesPreview from '../components/About/AboutServicesPreview';
import AboutApproach from '../components/About/AboutApproach';
import AboutTrust from '../components/About/AboutTrust';
import AboutMedia from '../components/About/AboutMedia';

export default function About() {
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  return (
    <>
      <Navbar onOpenAuth={() => setIsAuthOpen(true)} />
      <AboutHero />
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
