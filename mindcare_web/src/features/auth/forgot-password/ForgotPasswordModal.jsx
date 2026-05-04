import { useEffect, useRef } from 'react';
import Modal from '../../../components/Modal/Modal';
import styles from './styles/forgot-password.module.css';
import ForgotPasswordStepper from './ForgotPasswordStepper';
import { useForgotPassword } from './hooks/useForgotPassword';

export default function ForgotPasswordModal({ open, onClose }) {
  const state = useForgotPassword();
  const { step, reset, submitEmail, submitOtp, submitPassword, otp } = state;
  const modalRef = useRef(null);

  useEffect(() => {
    if (!open) reset();
  }, [open, reset]);

  // Re-focus first input when step changes
  useEffect(() => {
    if (!open) return;
    modalRef.current?.focusFirst();
  }, [open, step]);

  // Enter submits the current step (Escape + Tab handled by Modal)
  useEffect(() => {
    if (!open) return;

    const handler = (e) => {
      if (e.key === 'Enter' && !e.defaultPrevented) {
        if (step === 1) submitEmail();
        else if (step === 2) submitOtp(otp);
        else if (step === 3) submitPassword();
      }
    };

    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, step, otp, submitEmail, submitOtp, submitPassword]);

  return (
    <Modal
      ref={modalRef}
      open={open}
      onClose={onClose}
      ariaLabel="Восстановление пароля"
      zIndex={2100}
    >
      <div className={styles.body}>
        <ForgotPasswordStepper state={state} onClose={onClose} />
      </div>
    </Modal>
  );
}
