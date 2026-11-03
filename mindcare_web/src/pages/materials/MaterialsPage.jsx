import { useState } from 'react';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
// Баннер общий с главной (banner_slides CMS, placement='materials') —
// не отдельная копия PageHero.
import Hero from '../home/components/Hero';
import MaterialsLibrary from '../../features/materials/ui/MaterialsLibrary';
import { usePageTitle } from '../../hooks/usePageTitle';

const publicMaterialPath = (id) => `/materials/${id}`;

export default function MaterialsPage() {
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  usePageTitle('Материалы');

  return (
    <>
      <Navbar onOpenAuth={() => setIsAuthOpen(true)} />
      <main id="main-content">
        <Hero placement="materials" />

        <section className="section-wrap alt">
          <div className="container">
            <MaterialsLibrary getItemPath={publicMaterialPath} />
          </div>
        </section>
      </main>

      <Footer />
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </>
  );
}
