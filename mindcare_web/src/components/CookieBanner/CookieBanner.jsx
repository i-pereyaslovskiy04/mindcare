import { useState, useEffect } from 'react';
import styles from './CookieBanner.module.css';

const CookieIcon = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
    <circle cx="9" cy="9" r="7.5" stroke="rgba(201,185,154,0.65)" strokeWidth="1.3" fill="none" />
    <circle cx="6" cy="7" r="1" fill="rgba(201,185,154,0.65)" />
    <circle cx="11" cy="6" r="0.8" fill="rgba(201,185,154,0.65)" />
    <circle cx="10" cy="12" r="1" fill="rgba(201,185,154,0.65)" />
  </svg>
);

export default function CookieBanner() {
  const [isVisible, setIsVisible] = useState(false);
  const [isHiding, setIsHiding] = useState(false);

  useEffect(() => {
    const choice = localStorage.getItem('mindcare_cookie_choice');
    if (choice) return;

    const timer = setTimeout(() => setIsVisible(true), 900);
    return () => clearTimeout(timer);
  }, []);

  const handleClose = () => {
    setIsHiding(true);
    setTimeout(() => {
      setIsVisible(false);
      setIsHiding(false);
    }, 420);
  };

  const handleAccept = () => {
    localStorage.setItem('mindcare_cookie_choice', 'accepted');
    handleClose();
  };

  const handleDecline = () => {
    localStorage.setItem('mindcare_cookie_choice', 'declined');
    handleClose();
  };

  if (!isVisible) return null;

  return (
    <div
      className={`${styles.cookieBanner} ${
        isVisible && !isHiding ? styles.cookieVisible : ''
      } ${isHiding ? styles.cookieHiding : ''}`}
      role="region"
      aria-label="Уведомление об использовании cookies"
    >
      <div className={styles.cookieInner}>
        <div className={styles.cookieIcon}>
          <CookieIcon />
        </div>
        <p className={styles.cookieText}>
          Мы используем cookies.{' '}
          <a href="/privacy-policy">Политика персональных данных</a>.
        </p>
        <div className={styles.cookieActions}>
          <button
            className={styles.cookieBtnAccept}
            onClick={handleAccept}
            type="button"
          >
            Принять
          </button>
          <button
            className={styles.cookieBtnDecline}
            onClick={handleDecline}
            type="button"
          >
            Отклонить
          </button>
        </div>
      </div>
    </div>
  );
}
