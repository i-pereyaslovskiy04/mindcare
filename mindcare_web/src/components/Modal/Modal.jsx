import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { createPortal } from 'react-dom';
import styles from './Modal.module.css';

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

const Modal = forwardRef(function Modal(
  { open, onClose, ariaLabel, zIndex = 2000, children },
  ref
) {
  const cardRef = useRef(null);
  const prevFocusRef = useRef(null);

  useImperativeHandle(ref, () => ({
    focusFirst: () =>
      requestAnimationFrame(() =>
        cardRef.current?.querySelector(FOCUSABLE)?.focus()
      ),
  }));

  useEffect(() => {
    if (open) {
      prevFocusRef.current = document.activeElement;
      requestAnimationFrame(() =>
        cardRef.current?.querySelector(FOCUSABLE)?.focus()
      );
    } else {
      prevFocusRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const handler = (e) => {
      if (e.key === 'Escape') {
        onClose();
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
  }, [open, onClose]);

  return createPortal(
    <div
      className={`${styles.overlay} ${open ? styles.open : ''}`}
      style={{ zIndex }}
      aria-hidden={!open}
    >
      <div
        className={styles.card}
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
      >
        <div className={styles.head}>
          <div className={styles.brand}>
            Психо<span className={styles.brandEm}>логия</span> ДонГУ
          </div>
          <button
            className={styles.closeBtn}
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
        {children}
      </div>
    </div>,
    document.body
  );
});

export default Modal;
