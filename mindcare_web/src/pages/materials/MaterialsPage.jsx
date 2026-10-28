import { useState } from 'react';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
// Баннер общий с главной (banner_slides CMS, placement='materials') —
// не отдельная копия PageHero.
import Hero from '../home/components/Hero';
import MaterialsLibrary from '../../features/materials/ui/MaterialsLibrary';

const publicMaterialPath = (id) => `/materials/${id}`;

export default function MaterialsPage() {
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  return (
    <>
      <Navbar onOpenAuth={() => setIsAuthOpen(true)} />
      <Hero placement="materials" />

      <section className="section-wrap alt">
        <div className="container">
          <MaterialsLibrary getItemPath={publicMaterialPath} />
        </div>
      </section>

      <Footer />
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </>
  );
}
