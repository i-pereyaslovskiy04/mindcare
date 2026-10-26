import { useCallback, useEffect, useId, useRef, useState } from 'react';
import styles from './AuthModal.module.css';
import CodeInput from '../../../components/CodeInput/CodeInput';
import Checkbox from '../../../components/UI/Checkbox/Checkbox';

export const RESEND_COOLDOWN = 60;
export const EMPTY_CODE = Object.freeze(['', '', '', '', '', '']);

/** Состояние шага: ввод кода / идёт проверка / подтвердить уже нельзя. */
export const OTP_STATUS = Object.freeze({
  READY: 'ready',
  SUBMITTING: 'submitting',
  BLOCKED: 'blocked',
});

/** Задержка авто-подтверждения после ввода шестой цифры (мс). */
const AUTO_CONFIRM_DELAY = 120;

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
 * Шаг «Подтверждение регистрации» — ОДИН вид для всех способов регистрации:
 * по email и паролю (шаг кода в исходной вкладке), по ссылке из письма
 * (/register/confirm, только код) и через провайдера (Яндекс/VK). Заголовок,
 * описание, `CodeInput`, ошибка, необязательные согласие и повторная
 * отправка, кнопка «Подтвердить» и вторичное действие. Вкладок «Вход |
 * Регистрация» на этом шаге нет.
 *
 * Только разметка и UX. Шаг не знает ни адреса, куда ушёл код, ни reference
 * из ссылки, ни пароля, ни endpoint, ни навигации, ни правил автовхода —
 * это дело владельца (controller).
 *
 *   code / onCodeChange — массив из 6 цифр;
 *   onConfirm(code)     — подтвердить (вызывает владелец запросом к backend);
 *   description         — текст под заголовком (узел);
 *   status              — OTP_STATUS: ready | submitting | blocked;
 *   error               — текст ошибки (объявляется role="alert" и связан с
 *                         ячейками через aria-describedby);
 *   resend?             — { secondsLeft, onResend }: таймер и «Отправить повторно»;
 *   secondaryAction?    — { label, onClick }: «Изменить данные», «Начать заново»;
 *   consent?            — { checked, onChange, error, onMissing }: компактный
 *                         чекбокс согласия (регистрация через провайдера).
 *
 * Подтверждение — один раз на введённый код: автоматически после шестой
 * цифры, по Enter или кнопкой; повторные срабатывания до ответа владельца
 * (смены status или кода) отбрасываются. Во время проверки ячейки
 * недоступны. Фокус — на первой ячейке при открытии шага и после ошибки,
 * когда владелец очистил код.
 */
export default function RegistrationOtpStep({
  code,
  onCodeChange,
  onConfirm,
  description,
  status = OTP_STATUS.READY,
  error,
  resend,
  secondaryAction,
  consent,
}) {
  const errorId = useId();
  const titleId = useId();
  const codeRef = useRef(null);
  const ready = status === OTP_STATUS.READY;
  const submitting = status === OTP_STATUS.SUBMITTING;
  const consentMissing = consent ? !consent.checked : false;
  const complete = code.every((d) => d !== '');
  const empty = code.every((d) => d === '');
  const canConfirm = complete && ready && !consentMissing;

  // Свежий обработчик без перезапуска эффекта авто-подтверждения.
  const confirmRef = useRef(onConfirm);
  useEffect(() => { confirmRef.current = onConfirm; }, [onConfirm]);

  // Один confirm на код: авто-подтверждение, Enter и кнопка в одном кадре не
  // запускают параллельные запросы. Снимается, когда владелец ответил
  // (status не submitting) или код изменился.
  const pending = useRef(false);
  useEffect(() => {
    if (status !== OTP_STATUS.SUBMITTING) pending.current = false;
  }, [status, code]);

  const confirmOnce = useCallback((digits) => {
    if (pending.current) return;
    pending.current = true;
    confirmRef.current(digits);
  }, []);

  useEffect(() => {
    if (!canConfirm) return undefined;
    const id = setTimeout(() => confirmOnce(code), AUTO_CONFIRM_DELAY);
    return () => clearTimeout(id);
  }, [code, canConfirm, confirmOnce]);

  // Фокус на первую ячейку: при открытии шага и после ошибки (код очищен).
  // Modal при открытии ставит фокус на первый контрол в следующем кадре —
  // шаг, открытый вместе с модалкой, возвращает фокус себе после этого.
  useEffect(() => {
    if (!ready || !empty) return undefined;
    codeRef.current?.focus();
    let inner = 0;
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => codeRef.current?.focus());
    });
    return () => {
      cancelAnimationFrame(outer);
      cancelAnimationFrame(inner);
    };
  }, [ready, empty, error]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (consent && !consent.checked) {
      consent.onMissing();   // показать подсказку согласия
      return;
    }
    if (!complete || !ready) return;
    confirmOnce(code);
  };

  return (
    <form
      className={`${styles.authPanel} ${styles.active}`}
      onSubmit={handleSubmit}
      noValidate
      aria-labelledby={titleId}
    >
      <h2 className={styles.stepTitle} id={titleId}>Подтверждение регистрации</h2>
      {description && <p className={styles.stepDesc}>{description}</p>}

      <CodeInput
        ref={codeRef}
        value={code}
        onChange={onCodeChange}
        error={!!error}
        disabled={!ready}
        describedBy={errorId}
      />

      {error && (
        <div className={styles.apiError} id={errorId} role="alert">{error}</div>
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
                {/* Новая вкладка: переход в этой же вкладке выгружает страницу,
                    а ticket регистрации через провайдера живёт только в памяти. */}
                <a
                  href="/privacy-policy"
                  className={styles.consentLink}
                  target="_blank"
                  rel="noopener noreferrer"
                >
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

      {resend && status !== OTP_STATUS.BLOCKED && (resend.secondsLeft > 0 ? (
        <p className={styles.otpTimer}>
          Отправить повторно через{' '}
          <span className={styles.otpTimerCount}>{resend.secondsLeft}</span> с
        </p>
      ) : (
        <div className={styles.otpAux}>
          <button
            type="button"
            className={styles.ghost}
            onClick={resend.onResend}
            disabled={!ready}
          >
            Отправить повторно
          </button>
        </div>
      ))}

      <button
        type="submit"
        className={styles.authBtn}
        disabled={!ready || !complete}
      >
        {submitting ? 'Проверяем…' : 'Подтвердить'}
      </button>

      {secondaryAction && (
        <div className={styles.otpAux}>
          <button
            type="button"
            className={`${styles.ghost} ${styles.ghostMuted}`}
            onClick={secondaryAction.onClick}
            disabled={submitting}
          >
            {secondaryAction.label}
          </button>
        </div>
      )}
    </form>
  );
}
