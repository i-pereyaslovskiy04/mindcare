import { useState, useEffect, useRef, useCallback } from 'react';
import { authApi } from '../../AuthContext';

const TIMER_SEC = 60;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function useForgotPassword() {
  const [step, setStep]       = useState(1);
  const [email, setEmail]     = useState('');
  const [otp, setOtp]         = useState(Array(6).fill(''));
  const [password, setPassword]   = useState('');
  const [password2, setPassword2] = useState('');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors]   = useState({});
  const [timerSec, setTimerSec] = useState(0);

  // Keep loading in a ref so callbacks stay fresh without re-creating
  const loadingRef = useRef(false);
  useEffect(() => { loadingRef.current = loading; }, [loading]);

  // Countdown tick
  useEffect(() => {
    if (timerSec <= 0) return;
    const id = setTimeout(() => setTimerSec(s => s - 1), 1000);
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
      await authApi.passwordResetInit({ email: email.trim() });
      // Backend always returns 200 (safe — doesn't reveal if email exists).
      // Move to OTP step regardless.
      setStep(2);
      startTimer();
    } catch (err) {
      // 429 cooldown or 500 server error
      setErrors({ email: err.message || 'Ошибка. Попробуйте снова.' });
    } finally {
      setLoading(false);
    }
  }, [email, startTimer]);

  // ── Step 2: validate OTP locally, advance to password step ────────────────
  // The OTP is verified server-side together with the new password in step 3.
  // Here we only check that all digits are filled before proceeding.
  const submitOtp = useCallback((currentOtp) => {
    if (loadingRef.current) return;
    if (currentOtp.some(d => d === '')) {
      setErrors({ otp: 'Введите все 6 цифр кода' });
      return;
    }
    setErrors({});
    setStep(3);
  }, []);

  // ── Step 3: confirm OTP + set new password ─────────────────────────────────
  const submitPassword = useCallback(async () => {
    if (loadingRef.current) return;
    const errs = {};
    if (password.length < 8)               errs.password  = 'Минимум 8 символов';
    if (!password2 || password !== password2) errs.password2 = 'Пароли не совпадают';
    if (Object.keys(errs).length) { setErrors(errs); return; }

    setErrors({});
    setLoading(true);
    try {
      await authApi.passwordResetConfirm({
        email:        email.trim(),
        code:         otp.join(''),
        new_password: password,
      });
      setStep('done');
    } catch (err) {
      // OTP wrong / expired / attempts exceeded → back to OTP step
      setErrors({ otp: err.message || 'Неверный или истёкший код. Запросите новый.' });
      setStep(2);
    } finally {
      setLoading(false);
    }
  }, [email, otp, password, password2]);

  // ── Resend OTP (step 2) ────────────────────────────────────────────────────
  const resendOtp = useCallback(async () => {
    if (loadingRef.current) return;
    setOtp(Array(6).fill(''));
    setErrors({});
    setLoading(true);
    try {
      await authApi.passwordResetInit({ email: email.trim() });
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
    setStep(1);
    setEmail('');
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
