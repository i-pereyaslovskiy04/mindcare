import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import styles from './styles/forgot-password.module.css';
import ForgotPasswordStepper from './ForgotPasswordStepper';
import { useForgotPassword } from './hooks/useForgotPassword';

const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function ForgotPasswordModal({ open, onClose }) {
  const state = useForgotPassword();
  const { step, reset, submitEmail, submitOtp, submitPassword, otp } = state;
  const cardRef = useRef(null);
  const prevFocusRef = useRef(null);

  // Save / restore focus
  useEffect(() => {
    if (open) {
      prevFocusRef.current = document.activeElement;
      requestAnimationFrame(() => {
        cardRef.current?.querySelector(FOCUSABLE)?.focus();
      });
    } else {
      prevFocusRef.current?.focus();
    }
  }, [open]);

  // Re-focus first input on step change
  useEffect(() => {
    if (!open) return;
    requestAnimationFrame(() => {
      cardRef.current?.querySelector(FOCUSABLE)?.focus();
    });
  }, [open, step]);

  // Reset state when closed
  useEffect(() => {
    if (!open) reset();
  }, [open, reset]);

  // Keyboard: Escape + Tab trap + Enter submit
  useEffect(() => {
    if (!open) return;

    const handler = (e) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }

      if (e.key === 'Enter' && !e.defaultPrevented) {
        if (step === 1) submitEmail();
        else if (step === 2) submitOtp(otp);
        else if (step === 3) submitPassword();
        return;
      }

      if (e.key === 'Tab') {
        const focusable = Array.from(
          cardRef.current?.querySelectorAll(FOCUSABLE) ?? []
        );
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey) {
          if (document.activeElement === first) { e.preventDefault(); last.focus(); }
        } else {
          if (document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      }
    };

    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, step, otp, onClose, submitEmail, submitOtp, submitPassword]);

  const handleOverlay = (e) => {
    if (e.target === e.currentTarget) onClose();
  };

  return createPortal(
    <div
      className={`${styles.overlay} ${open ? styles.overlayOpen : ''}`}
      onClick={handleOverlay}
      aria-hidden={!open}
    >
      <div
        className={styles.card}
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-label="Восстановление пароля"
      >
        <div className={styles.head}>
          <div className={styles.brand}>
            Психо<span className={styles.brandEm}>логия</span> ДонГУ
          </div>
          <button
            className={styles.closeBtn}
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
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

        <ForgotPasswordStepper state={state} onClose={onClose} />
      </div>
    </div>,
    document.body
  );
}
