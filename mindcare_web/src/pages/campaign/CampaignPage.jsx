import { useState } from 'react';
import { useParams } from 'react-router-dom';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
import PublicCampaign from '../../features/campaigns/ui/PublicCampaign';
import { usePageTitle } from '../../hooks/usePageTitle';
import styles from './CampaignPage.module.css';

/** /test/:token (и прежний /c/:token) — тестирование по ссылке кампании без входа (ADR-036). */
export default function CampaignPage() {
  const { token } = useParams();
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  usePageTitle('Тестирование');

  return (
    <>
      <Navbar onOpenAuth={() => setIsAuthOpen(true)} />
      <main id="main-content" className={styles.main}>
        <PublicCampaign key={token} token={token} />
      </main>
      <Footer />
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </>
  );
}
