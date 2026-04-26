import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import styles from './Navbar.module.css';

const NAV_LINKS = [
  { label: 'Главная', to: '/' },
  { label: 'О нас', href: '#' },
  { label: 'Услуги', href: '#' },
  { label: 'Материалы', href: '#' },
];

const UserIcon = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
    <circle cx="9" cy="6.5" r="3.5" stroke="rgba(139,111,71,0.65)" strokeWidth="1.4" fill="none" />
    <path
      d="M2 17c0-3.866 3.134-7 7-7s7 3.134 7 7"
      stroke="rgba(139,111,71,0.65)"
      strokeWidth="1.4"
      fill="none"
    />
  </svg>
);

const BurgerIcon = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
    <path d="M2 4.5h14M2 9h14M2 13.5h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const CloseIcon = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
    <path d="M3 3l12 12M15 3L3 15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

export default function Navbar({ onOpenAuth }) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  // Close menu when resizing back to desktop
  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth > 768) setIsMenuOpen(false);
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const closeMenu = () => setIsMenuOpen(false);

  const handleAuthClick = () => {
    closeMenu();
    onOpenAuth();
  };

  return (
    <nav className={styles.navbar}>
      <div className={styles.navFull}>
        <div className={styles.navLogo}>
          Психо<span className={styles.navLogoHighlight}>логия</span> ДонГУ
        </div>

        {/* Desktop nav links — hidden on mobile via CSS */}
        <ul className={styles.navLinks}>
          {NAV_LINKS.map((link) => (
            <li key={link.label}>
              {link.to
                ? <Link to={link.to}>{link.label}</Link>
                : <a href={link.href}>{link.label}</a>}
            </li>
          ))}
        </ul>

        {/* Right side: user icon (always) + burger (mobile only) */}
        <div className={styles.navRight}>
          <button
            className={styles.navUserIcon}
            onClick={onOpenAuth}
            aria-label="Войти в аккаунт"
            type="button"
          >
            <UserIcon />
          </button>
          <button
            className={styles.navBurger}
            onClick={() => setIsMenuOpen((prev) => !prev)}
            aria-label={isMenuOpen ? 'Закрыть меню' : 'Открыть меню'}
            aria-expanded={isMenuOpen}
            aria-controls="mobile-menu"
            type="button"
          >
            {isMenuOpen ? <CloseIcon /> : <BurgerIcon />}
          </button>
        </div>
      </div>

      {/* Mobile drawer */}
      <div
        id="mobile-menu"
        className={`${styles.mobileMenu} ${isMenuOpen ? styles.mobileMenuOpen : ''}`}
        aria-hidden={!isMenuOpen}
      >
        <ul className={styles.mobileNavLinks}>
          {NAV_LINKS.map((link) => (
            <li key={link.label}>
              {link.to
                ? <Link to={link.to} onClick={closeMenu}>{link.label}</Link>
                : <a href={link.href} onClick={closeMenu}>{link.label}</a>}
            </li>
          ))}
        </ul>
        <button className={styles.mobileAuthBtn} onClick={handleAuthClick} type="button">
          Войти в аккаунт
        </button>
      </div>
    </nav>
  );
}
