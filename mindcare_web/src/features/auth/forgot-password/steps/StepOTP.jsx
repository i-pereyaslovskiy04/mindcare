import { useEffect, useRef } from 'react';
import styles from '../styles/forgot-password.module.css';
import OTPInput from '../components/OTPInput';

const ERROR_ID = 'fp-otp-error';

/**
 * Шаг 2: код. Форма — Enter в ячейке отправляет только этот шаг.
 * fieldRef — CodeInput ({ focus() } — первая ячейка).
 *
 * Автоотправка — только после ввода пользователем: при возврате на шаг
 * («← Изменить код» или неверный код с шага 3) прежний полный код остаётся для
 * правки, но сам не отправляется и не уводит обратно на шаг 3.
 */
export default function StepOTP({
  email, otp, setOtp, errors, setErrors,
  loading, timerSec, onSubmit, onResend, onBack, fieldRef,
}) {
  const edited = useRef(false);

  // Auto-submit when all 6 digits are filled by the user
  useEffect(() => {
    if (!edited.current || !otp.every(d => d !== '')) return undefined;
    const id = setTimeout(() => onSubmit(otp), 120);
    return () => clearTimeout(id);
  }, [otp, onSubmit]);

  const handleOtpChange = (next) => {
    edited.current = true;
    setOtp(next);
    if (errors.otp) setErrors(prev => ({ ...prev, otp: null }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (onSubmit(otp)) fieldRef?.current?.focus();
  };

  return (
    <form className={styles.panel} onSubmit={handleSubmit} noValidate>
      <div>
        <h2 className={styles.heading}>
          Введите <span className={styles.headingEm}>код</span>
        </h2>
        <p className={styles.lead}>
          Отправили 6-значный код на{' '}
          <strong className={styles.leadStrong}>{email}</strong>
        </p>
      </div>

      <OTPInput
        ref={fieldRef}
        value={otp}
        onChange={handleOtpChange}
        error={!!errors.otp}
        describedBy={errors.otp ? ERROR_ID : undefined}
      />

      {errors.otp && (
        <span id={ERROR_ID} className={styles.hint} role="alert">
          {errors.otp}
        </span>
      )}

      <div className={styles.aux}>
        {timerSec > 0 ? (
          <span className={styles.timer}>
            Отправить повторно через{' '}
            <span className={styles.timerCount}>{timerSec}</span> с
          </span>
        ) : (
          <button className={styles.ghost} type="button" onClick={onResend}>
            Отправить повторно
          </button>
        )}
      </div>

      <div className={styles.actions}>
        <button
          className={`${styles.btn} ${styles.btnPrimary} ${loading ? styles.btnLoading : ''}`}
          type="submit"
          disabled={loading}
        >
          {loading ? <span className={styles.spinner} /> : 'Подтвердить'}
        </button>
        <button className={`${styles.ghost} ${styles.ghostMuted}`} type="button" onClick={onBack}>
          ← Изменить почту
        </button>
      </div>
    </form>
  );
}
