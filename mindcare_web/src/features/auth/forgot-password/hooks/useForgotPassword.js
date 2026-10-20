import { useState, useEffect, useRef, useCallback } from 'react';
import { passwordResetInit, passwordResetConfirm } from '../../../../api/auth.api';

const TIMER_SEC = 60;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Сценарий восстановления/установки пароля по email-коду.
 *
 * Опции (все необязательны — публичный сценарий «Забыли пароль» работает как прежде):
 *   initialEmail — email, с которого начинается сценарий (и к которому возвращает reset);
 *   onCompleted  — вызывается РОВНО ОДИН раз сразу после успешного подтверждения
 *                  нового пароля, даже если окно закрыли, пока шёл финальный запрос
 *                  (результат запроса не теряется; запоздавшие обновления UI отбрасываются).
 */
export function useForgotPassword({ initialEmail = '', onCompleted } = {}) {
  const [step, setStep]           = useState(1);
  const [email, setEmail]         = useState(initialEmail);
  const [otp, setOtp]             = useState(Array(6).fill(''));
  const [password, setPassword]   = useState('');
  const [password2, setPassword2] = useState('');
  const [loading, setLoading]     = useState(false);
  const [errors, setErrors]       = useState({});
  const [timerSec, setTimerSec]   = useState(0);

  const loadingRef = useRef(false);
  const onCompletedRef = useRef(onCompleted);
  const initialEmailRef = useRef(initialEmail);
  const completedRef = useRef(false);   // onCompleted уже вызван для этого сценария
  const confirmInFlightRef = useRef(false);
  const genRef = useRef(0);             // поколение сценария: reset() его меняет
  useEffect(() => {
    onCompletedRef.current = onCompleted;
    initialEmailRef.current = initialEmail;
  });
  useEffect(() => { loadingRef.current = loading; }, [loading]);

  // Countdown tick
  useEffect(() => {
    if (timerSec <= 0) return;
    const id = setTimeout(() => setTimerSec((s) => s - 1), 1000);
    return () => clearTimeout(id);
  }, [timerSec]);

  const startTimer = useCallback(() => setTimerSec(TIMER_SEC), []);

  // ── Step 1: send reset OTP ─────────────────────────────────────────────────
  const submitEmail = useCallback(async () => {
    if (loadingRef.current) return;
    if (!EMAIL_RE.test(email.trim())) {
      setErrors({ email: 'Введите корректный email' });
      return;
    }
    setErrors({});
    setLoading(true);
    try {
      await passwordResetInit({ email: email.trim() });
      setStep(2);
      startTimer();
    } catch (err) {
      setErrors({ email: err.message || 'Ошибка. Попробуйте снова.' });
    } finally {
      setLoading(false);
    }
  }, [email, startTimer]);

  // ── Step 2: local OTP validation only — server verifies in step 3 ─────────
  const submitOtp = useCallback((currentOtp) => {
    if (loadingRef.current) return;
    if (currentOtp.some((d) => d === '')) {
      setErrors({ otp: 'Введите все 6 цифр кода' });
      return;
    }
    setErrors({});
    setStep(3);
  }, []);

  // ── Step 3: confirm OTP + set new password ─────────────────────────────────
  const submitPassword = useCallback(async () => {
    if (loadingRef.current || confirmInFlightRef.current) return;
    const errs = {};
    if (password.length < 8)                errs.password  = 'Минимум 8 символов';
    if (!password2 || password !== password2) errs.password2 = 'Пароли не совпадают';
    if (Object.keys(errs).length) { setErrors(errs); return; }

    setErrors({});
    setLoading(true);
    confirmInFlightRef.current = true;
    const gen = genRef.current;
    let confirmed = false;
    try {
      await passwordResetConfirm({
        email:        email.trim(),
        code:         otp.join(''),
        new_password: password,
      });
      confirmed = true;
    } catch (err) {
      // Wrong/expired OTP → back to OTP step (если сценарий не сброшен закрытием окна)
      if (gen === genRef.current) {
        setErrors({ otp: err.message || 'Неверный или истёкший код. Запросите новый.' });
        setStep(2);
      }
    } finally {
      confirmInFlightRef.current = false;
      if (gen === genRef.current) setLoading(false);
    }
    if (!confirmed) return;
    // Пароль изменён на сервере: результат учитываем независимо от того, открыто ли окно.
    if (!completedRef.current) {
      completedRef.current = true;
      onCompletedRef.current?.();
    }
    if (gen === genRef.current) setStep('done');
  }, [email, otp, password, password2]);

  // ── Resend OTP ─────────────────────────────────────────────────────────────
  const resendOtp = useCallback(async () => {
    if (loadingRef.current) return;
    setOtp(Array(6).fill(''));
    setErrors({});
    setLoading(true);
    try {
      await passwordResetInit({ email: email.trim() });
      startTimer();
    } catch (err) {
      setErrors({ otp: err.message || 'Не удалось отправить код. Попробуйте снова.' });
    } finally {
      setLoading(false);
    }
  }, [email, startTimer]);

  const goBack = useCallback((targetStep) => {
    setErrors({});
    setStep(targetStep);
  }, []);

  const reset = useCallback(() => {
    genRef.current += 1;
    completedRef.current = false;
    setStep(1);
    setEmail(initialEmailRef.current);
    setOtp(Array(6).fill(''));
    setPassword('');
    setPassword2('');
    setErrors({});
    setTimerSec(0);
    setLoading(false);
  }, []);

  return {
    step,
    email, setEmail,
    otp, setOtp,
    password, setPassword,
    password2, setPassword2,
    loading,
    errors, setErrors,
    timerSec,
    submitEmail,
    submitOtp,
    submitPassword,
    resendOtp,
    goBack,
    reset,
  };
}
