import { useState } from 'react';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../components/AuthModal/AuthModal';
import PageHero from '../../components/Hero/PageHero';
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
      <PageHero
        eyebrow="Донецкий государственный университет"
        title={<>Ресурсный центр<br />практической психологии</>}
        sub="Психологическая помощь и поддержка студентов, преподавателей и сотрудников ДонГУ"
      />
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
