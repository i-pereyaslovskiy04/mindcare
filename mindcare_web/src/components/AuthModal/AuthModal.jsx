import { useState, useRef, useEffect, useCallback } from 'react';
import styles from './AuthModal.module.css';
import LoginForm from './LoginForm';
import RegisterForm from './RegisterForm';
import ForgotPasswordModal from '../../features/auth/forgot-password/ForgotPasswordModal';

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function AuthModal({ isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('login');
  const [forgotOpen, setForgotOpen] = useState(false);

  const handleForgotPassword = useCallback(() => {
    onClose();
    setForgotOpen(true);
  }, [onClose]);
  const cardRef = useRef(null);
  const previousFocusRef = useRef(null);

  // Save focus before opening; restore when closed.
  useEffect(() => {
    if (isOpen) {
      previousFocusRef.current = document.activeElement;
      requestAnimationFrame(() => {
        const focusable = cardRef.current?.querySelectorAll(FOCUSABLE_SELECTOR);
        focusable?.[0]?.focus();
      });
    } else {
      previousFocusRef.current?.focus();
    }
  }, [isOpen]);

  // Escape + focus trap attached to document when modal is open.
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }

      if (e.key === 'Tab') {
        const focusable = Array.from(
          cardRef.current?.querySelectorAll(FOCUSABLE_SELECTOR) ?? []
        );
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const handleOverlayClick = useCallback(
    (e) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose]
  );

  return (
    <>
    <div
      className={`${styles.authOverlay} ${isOpen ? styles.isOpen : ''}`}
      onClick={handleOverlayClick}
      aria-hidden={!isOpen}
    >
      <div
        className={styles.authCard}
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-dialog-title"
      >
        <div className={styles.authHead}>
          <div className={styles.authBrand} id="auth-dialog-title">
            Психо<span className={styles.authBrandHighlight}>логия</span> ДонГУ
          </div>
          <button
            className={styles.authClose}
            onClick={onClose}
            aria-label="Закрыть"
            type="button"
          >
            <svg width="11" height="11" viewBox="0 0 11 11" fill="none" aria-hidden="true">
              <path
                d="M1 1l9 9M10 1L1 10"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>

        <div className={styles.authBody}>
          <div
            className={`${styles.authTabs} ${activeTab === 'register' ? styles.onRegister : ''}`}
            role="tablist"
            aria-label="Тип формы"
          >
            <div className={styles.authTabsPill} aria-hidden="true" />
            <button
              className={`${styles.authTabBtn} ${activeTab === 'login' ? styles.active : ''}`}
              onClick={() => setActiveTab('login')}
              type="button"
              role="tab"
              aria-selected={activeTab === 'login'}
              aria-controls="panel-login"
              id="tab-login"
            >
              Вход
            </button>
            <button
              className={`${styles.authTabBtn} ${activeTab === 'register' ? styles.active : ''}`}
              onClick={() => setActiveTab('register')}
              type="button"
              role="tab"
              aria-selected={activeTab === 'register'}
              aria-controls="panel-register"
              id="tab-register"
            >
              Регистрация
            </button>
          </div>

          <div className={styles.authPanels}>
            {/*
              Both forms stay mounted to preserve state on tab switch.
              The `hidden` attribute (display:none via UA stylesheet) removes
              inactive panels from tab order and re-triggers CSS animation
              on the child form each time the panel becomes visible.
            */}
            <div
              id="panel-login"
              role="tabpanel"
              aria-labelledby="tab-login"
              hidden={activeTab !== 'login'}
            >
              <LoginForm onSuccess={onClose} onForgotPassword={handleForgotPassword} />
            </div>
            <div
              id="panel-register"
              role="tabpanel"
              aria-labelledby="tab-register"
              hidden={activeTab !== 'register'}
            >
              <RegisterForm onSuccess={onClose} />
            </div>
          </div>
        </div>
      </div>
    </div>

    <ForgotPasswordModal
      open={forgotOpen}
      onClose={() => setForgotOpen(false)}
    />
    </>
  );
}
