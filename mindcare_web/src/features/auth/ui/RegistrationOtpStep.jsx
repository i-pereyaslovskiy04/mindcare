import { useCallback, useEffect, useRef, useState } from 'react';
import styles from './AuthModal.module.css';
import CodeInput from '../../../components/CodeInput/CodeInput';
import Checkbox from '../../../components/UI/Checkbox/Checkbox';

export const RESEND_COOLDOWN = 60;
export const EMPTY_CODE = Object.freeze(['', '', '', '', '', '']);

/**
 * Обратный отсчёт до повторной отправки кода: [секунды, перезапуск].
 * initialSeconds — значение с первого кадра (код уже отправлен до монтирования).
 */
export function useResendTimer(initialSeconds = 0) {
  const [timer, setTimer] = useState(initialSeconds);
  useEffect(() => {
    if (timer <= 0) return undefined;
    const id = setTimeout(() => setTimer((t) => t - 1), 1000);
    return () => clearTimeout(id);
  }, [timer]);
  const restart = useCallback(() => setTimer(RESEND_COOLDOWN), []);
  return [timer, restart];
}

/**
 * Шаг «Подтверждение регистрации» — общий для регистрации по email и паролю
 * и для регистрации через Яндекс (Stage Social Auth 4): заголовок, адрес, куда
 * ушёл код, `CodeInput`, таймер и повторная отправка, кнопка «Подтвердить» и
 * ссылка назад. Вкладок «Вход | Регистрация» на этом шаге нет — это уже не
 * выбор режима, а подтверждение.
 *
 * Только разметка и UX: запросы к backend делает владелец шага (onConfirm,
 * onResend). Когда введены все 6 цифр, onConfirm вызывается автоматически —
 * если подтверждение сейчас допустимо (нет загрузки, согласие при наличии
 * чекбокса отмечено, шаг не заблокирован).
 *
 * consent — необязательный компактный чекбокс согласия MindCare:
 *   { checked, onChange, error, onMissing } (регистрация через Яндекс; у
 *   регистрации по паролю согласие уже принято на первом шаге). onMissing —
 *   нажали «Подтвердить» без согласия: показать подсказку.
 */
export default function RegistrationOtpStep({
  email,
  code,
  onCodeChange,
  error,
  timer,
  onResend,
  onConfirm,
  loading = false,
  blocked = false,
  consent,
  backLabel,
  onBack,
}) {
  const consentMissing = consent ? !consent.checked : false;
  const complete = code.every((d) => d !== '');
  const canConfirm = complete && !loading && !blocked && !consentMissing;

  // Свежий обработчик без перезапуска эффекта авто-подтверждения.
  const confirmRef = useRef(onConfirm);
  useEffect(() => { confirmRef.current = onConfirm; }, [onConfirm]);

  useEffect(() => {
    if (!canConfirm) return undefined;
    const id = setTimeout(() => confirmRef.current(code), 120);
    return () => clearTimeout(id);
  }, [code, canConfirm]);

  const handleConfirmClick = () => {
    if (consent && !consent.checked) {
      consent.onMissing();   // показать подсказку согласия
      return;
    }
    onConfirm(code);
  };

  return (
    <div className={`${styles.authPanel} ${styles.active}`}>
      <h2 className={styles.stepTitle}>Подтверждение регистрации</h2>
      <p className={styles.stepDesc}>
        Отправили 6-значный код на{' '}
        <strong className={styles.stepDescStrong}>{email}</strong>
      </p>

      <CodeInput value={code} onChange={onCodeChange} error={!!error} />

      {error && (
        <div className={styles.apiError} role="alert">{error}</div>
      )}

      {consent && (
        <>
          <Checkbox
            id="otp-consent"
            checked={consent.checked}
            onChange={consent.onChange}
            label={
              <>
                Согласен(на) с{' '}
                <a href="/privacy-policy" className={styles.consentLink}>
                  политикой персональных данных
                </a>
              </>
            }
            error={consent.error}
            ariaDescribedBy={consent.error ? 'otp-consent-hint' : undefined}
          />
          {consent.error && (
            <span className={styles.consentHint} id="otp-consent-hint" role="alert">
              Необходимо принять политику персональных данных
            </span>
          )}
        </>
      )}

      {!blocked && (timer > 0 ? (
        <p className={styles.otpTimer}>
          Отправить повторно через{' '}
          <span className={styles.otpTimerCount}>{timer}</span> с
        </p>
      ) : (
        <div className={styles.otpAux}>
          <button
            type="button"
            className={styles.ghost}
            onClick={onResend}
            disabled={loading}
          >
            Отправить повторно
          </button>
        </div>
      ))}

      <button
        type="button"
        className={styles.authBtn}
        onClick={handleConfirmClick}
        disabled={loading || blocked || !complete}
      >
        {loading ? 'Проверяем…' : 'Подтвердить'}
      </button>

      <div className={styles.otpAux}>
        <button
          type="button"
          className={`${styles.ghost} ${styles.ghostMuted}`}
          onClick={onBack}
        >
          {backLabel}
        </button>
      </div>
    </div>
  );
}
