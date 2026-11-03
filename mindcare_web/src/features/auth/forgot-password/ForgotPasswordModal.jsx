import { useEffect, useRef } from 'react';
import Modal from '../../../components/Modal/Modal';
import styles from './styles/forgot-password.module.css';
import ForgotPasswordStepper from './ForgotPasswordStepper';
import { useForgotPassword } from './hooks/useForgotPassword';

/**
 * Props: open, onClose; необязательные — initialEmail, emailLocked (email нельзя менять,
 * например при установке пароля из настроек), onCompleted (см. useForgotPassword).
 */
export default function ForgotPasswordModal({
  open, onClose, initialEmail = '', emailLocked = false, onCompleted,
}) {
  const state = useForgotPassword({ initialEmail, onCompleted });
  const { step, reset } = state;
  const modalRef = useRef(null);
  // Основное поле текущего шага (см. ForgotPasswordStepper).
  const fieldRef = useRef(null);
  const contentRef = useRef(null);

  useEffect(() => {
    if (!open) reset();
  }, [open, reset, initialEmail]);

  // Открытие и смена шага: фокус на основное поле шага, а не на «Закрыть».
  // rAF — после собственного фокуса Modal при открытии. Если пользователь уже
  // в поле этого шага, фокус не перехватывается.
  useEffect(() => {
    if (!open) return undefined;
    const id = requestAnimationFrame(() => {
      const active = document.activeElement;
      if (active?.tagName === 'INPUT' && contentRef.current?.contains(active)) return;
      if (fieldRef.current) fieldRef.current.focus();
      else modalRef.current?.focusFirst();
    });
    return () => cancelAnimationFrame(id);
  }, [open, step]);

  // Enter отправляет только текущую форму шага (нативный submit): глобального
  // обработчика Enter нет — Enter на «Закрыть», «Изменить почту/код» шаг не
  // отправляет. Escape и Tab — в Modal.
  return (
    <Modal
      ref={modalRef}
      open={open}
      onClose={onClose}
      ariaLabel="Восстановление пароля"
      zIndex={2100}
    >
      <div ref={contentRef} className={styles.content}>
        <ForgotPasswordStepper
          state={state}
          onClose={onClose}
          emailLocked={emailLocked}
          fieldRef={fieldRef}
        />
      </div>
    </Modal>
  );
}
