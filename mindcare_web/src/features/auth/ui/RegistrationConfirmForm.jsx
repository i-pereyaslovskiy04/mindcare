import { useRef, useState } from 'react';
import styles from './AuthModal.module.css';
import { registerConfirm } from '../../../api/auth.api';
import RegistrationOtpStep, { EMPTY_CODE, OTP_STATUS } from './RegistrationOtpStep';

export const CONFIRM_FALLBACK_ERROR = 'Не удалось подтвердить регистрацию. Попробуйте снова.';

export const REFERENCE_MISSING_MESSAGE =
  'Эта ссылка не содержит данных для продолжения регистрации. Начните регистрацию заново.';
export const REFERENCE_INVALID_MESSAGE =
  'Ссылка недействительна или срок её действия истёк. Начните регистрацию заново.';
export const CODE_EXPIRED_MESSAGE = 'Срок действия кода истёк. Начните регистрацию заново.';
export const ATTEMPTS_EXHAUSTED_MESSAGE =
  'Попытки ввода кода исчерпаны. Начните регистрацию заново.';

// Машинные коды backend, после которых этим кодом регистрацию не завершить:
// остаётся только начать её заново. Состояние выбирается по code, не по тексту.
const TERMINAL_MESSAGES = Object.freeze({
  registration_reference_invalid: REFERENCE_INVALID_MESSAGE,
  otp_expired: CODE_EXPIRED_MESSAGE,
  otp_attempts_exhausted: ATTEMPTS_EXHAUSTED_MESSAGE,
});

function readableError(err) {
  const m = err?.message;
  return typeof m === 'string' && m && !/^HTTP \d+$/.test(m) ? m : CONFIRM_FALLBACK_ERROR;
}

/**
 * «Подтверждение регистрации» по ссылке из письма (/register/confirm#r=<uuid>):
 * тонкий controller над общим RegistrationOtpStep. Пользователь вводит ТОЛЬКО
 * код: выпуск кода выбирает registrationReference (из fragment ссылки,
 * разбирает владелец), email не нужен.
 *
 * Хранит только код. Reference не показывается и уходит на backend только в
 * теле POST ({ registration_reference, code }). Пароль здесь неизвестен —
 * автоматического входа нет: onConfirmed(email) получает email из ответа
 * backend (только после успешной регистрации), владелец показывает вход.
 *
 * Нет reference (старое письмо, обрезанная ссылка) или он недействителен,
 * код истёк, попытки исчерпаны — экран с объяснением и одним действием
 * «Начать регистрацию заново» (onRestart). Повторной отправки по reference
 * нет: новый код даёт только обычная форма регистрации.
 */
export default function RegistrationConfirmForm({ registrationReference, onConfirmed, onRestart }) {
  const [code, setCode] = useState(EMPTY_CODE);
  const [error, setError] = useState('');
  const [status, setStatus] = useState(OTP_STATUS.READY);
  const [terminal, setTerminal] = useState(null);   // { message, announce }
  const confirming = useRef(false);

  if (!registrationReference || terminal) {
    const message = terminal?.message ?? REFERENCE_MISSING_MESSAGE;
    return (
      <div className={`${styles.authPanel} ${styles.active}`}>
        <h2 className={styles.stepTitle}>Подтверждение регистрации</h2>
        <p className={styles.stepDesc} role={terminal?.announce ? 'alert' : undefined}>
          {message}
        </p>
        <button type="button" className={styles.authBtn} onClick={onRestart}>
          Начать регистрацию заново
        </button>
      </div>
    );
  }

  const handleConfirm = async (digits) => {
    const value = digits.join('');
    if (value.length < 6 || confirming.current) return;
    confirming.current = true;
    setError('');
    setStatus(OTP_STATUS.SUBMITTING);
    try {
      const data = await registerConfirm({ registrationReference, code: value });
      onConfirmed(typeof data?.email === 'string' ? data.email : '');
    } catch (err) {
      const terminalMessage = TERMINAL_MESSAGES[err?.code];
      if (terminalMessage) {
        setTerminal({ message: terminalMessage, announce: true });
        return;
      }
      setError(readableError(err));
      setCode(EMPTY_CODE);
      setStatus(OTP_STATUS.READY);
    } finally {
      confirming.current = false;
    }
  };

  return (
    <RegistrationOtpStep
      description="Введите 6-значный код из письма."
      code={code}
      onCodeChange={(next) => { setCode(next); setError(''); }}
      error={error}
      onConfirm={handleConfirm}
      status={status}
      secondaryAction={{ label: 'Начать регистрацию заново', onClick: onRestart }}
    />
  );
}
