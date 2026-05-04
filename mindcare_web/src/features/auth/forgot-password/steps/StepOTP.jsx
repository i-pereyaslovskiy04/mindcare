import { useEffect } from 'react';
import styles from '../styles/forgot-password.module.css';
import OTPInput from '../components/OTPInput';

export default function StepOTP({
  email, otp, setOtp, errors, setErrors,
  loading, timerSec, onSubmit, onResend, onBack,
}) {
  // Auto-submit when all 6 digits are filled
  useEffect(() => {
    if (otp.every(d => d !== '')) {
      const id = setTimeout(() => onSubmit(otp), 120);
      return () => clearTimeout(id);
    }
  }, [otp, onSubmit]);

  const handleOtpChange = (next) => {
    setOtp(next);
    if (errors.otp) setErrors(prev => ({ ...prev, otp: null }));
  };

  const timerVisible = timerSec > 0;

  return (
    <div className={styles.panel}>
      <div>
        <h2 className={styles.heading}>
          Введите <span className={styles.headingEm}>код</span>
        </h2>
        <p className={styles.body} style={{ marginTop: 6 }}>
          Отправили 6-значный код на{' '}
          <strong className={styles.bodyStrong}>{email}</strong>
        </p>
      </div>

      <div className={styles.divider} />

      <OTPInput
        value={otp}
        onChange={handleOtpChange}
        error={!!errors.otp}
      />

      {errors.otp && (
        <span className={`${styles.hint} ${styles.hintError}`} role="alert">
          {errors.otp}
        </span>
      )}

      <div className={timerVisible ? styles.timer : styles.timerHidden}>
        Отправить повторно через{' '}
        <span className={styles.timerCount}>{timerSec}</span> с
      </div>

      <div className={styles.aux}>
        {!timerVisible && (
          <button className={styles.ghost} type="button" onClick={onResend}>
            Отправить повторно
          </button>
        )}
      </div>

      <button
        className={`${styles.btn} ${styles.btnPrimary} ${loading ? styles.btnLoading : ''}`}
        type="button"
        onClick={() => onSubmit(otp)}
        disabled={loading}
      >
        {loading ? <span className={styles.spinner} /> : 'Подтвердить'}
      </button>

      <div className={styles.aux}>
        <button className={`${styles.ghost} ${styles.ghostMuted}`} type="button" onClick={onBack}>
          ← Изменить почту
        </button>
      </div>
    </div>
  );
}
