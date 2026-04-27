import { useState } from 'react';
import { Link } from 'react-router-dom';
import Navbar from '../../components/Navbar/Navbar';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../components/AuthModal/AuthModal';
import PageHero from '../../components/Hero/PageHero';
import ServicesSlider from './components/ServicesSlider';
import ProcessBlock from './components/ProcessBlock';
import PrinciplesBlock from './components/PrinciplesBlock';
import styles from './Services.module.css';

export default function Services() {
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  return (
    <>
      <Navbar onOpenAuth={() => setIsAuthOpen(true)} />

      <PageHero
        eyebrow="Донецкий государственный университет"
        title={<>Центр психологической<br />помощи ДонГУ</>}
        sub="Поддержка, развитие и психологическое благополучие студентов и сотрудников университета. Мы помогаем справляться с трудностями и находить внутренние ресурсы."
      />

      <section className="section-wrap alt">
        <div className="container">
          <ServicesSlider />
        </div>
      </section>

      <section className="section-wrap">
        <div className="container">
          <ProcessBlock />
        </div>
      </section>

      <section className="section-wrap alt">
        <div className="container">
          <PrinciplesBlock />
        </div>
      </section>

      <section className={`section-wrap ${styles.ctaSection}`}>
        <div className="container">
          <h2 className={styles.ctaTitle}>Не смогли определиться?</h2>
          <p className={styles.ctaSub}>
            Вы можете записаться на бесплатную консультацию или позвонить по номеру
            +7 (949) 312-22-55, где мы обсудим ваши потребности и подберём
            оптимальный вариант поддержки. Мы здесь, чтобы сделать процесс
            выбора простым и комфортным.
          </p>
          <Link to="/" className={styles.ctaBtn}>Записаться на консультацию</Link>
        </div>
      </section>

      <Footer />
      <AuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </>
  );
}
