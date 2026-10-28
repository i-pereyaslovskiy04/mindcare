import { useState } from 'react';
import { useParams } from 'react-router-dom';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
import MaterialView from '../../features/materials/ui/MaterialView';
import styles from './MaterialsItemPage.module.css';

export default function MaterialsItemPage() {
  const { id } = useParams();
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  return (
    <>
      <Navbar onOpenAuth={() => setIsAuthOpen(true)} />

      <div className={styles.pageWrap}>
        <div className={`container ${styles.pageInner}`}>
          <MaterialView uuid={id} backTo="/materials" fullBleed />
        </div>
      </div>

      <Footer />
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </>
  );
}
