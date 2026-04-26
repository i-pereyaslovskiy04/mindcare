import { useState, useEffect, useRef, useCallback } from 'react';

const TIMER_SEC = 60;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function useForgotPassword() {
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState(Array(6).fill(''));
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});
  const [timerSec, setTimerSec] = useState(0);

  // Keep loading in a ref so callbacks don't go stale on it
  const loadingRef = useRef(false);
  useEffect(() => { loadingRef.current = loading; }, [loading]);

  // Countdown tick
  useEffect(() => {
    if (timerSec <= 0) return;
    const id = setTimeout(() => setTimerSec(s => s - 1), 1000);
    return () => clearTimeout(id);
  }, [timerSec]);

  const startTimer = useCallback(() => setTimerSec(TIMER_SEC), []);

  const submitEmail = useCallback(async () => {
    if (loadingRef.current) return;
    if (!EMAIL_RE.test(email.trim())) {
      setErrors({ email: 'Введите корректный email' });
      return;
    }
    setErrors({});
    setLoading(true);
    await new Promise(r => setTimeout(r, 800));
    setLoading(false);
    setStep(2);
    startTimer();
  }, [email, startTimer]);

  const submitOtp = useCallback(async (currentOtp) => {
    if (loadingRef.current) return;
    if (currentOtp.some(d => d === '')) {
      setErrors({ otp: 'Введите все 6 цифр кода' });
      return;
    }
    setErrors({});
    setLoading(true);
    await new Promise(r => setTimeout(r, 700));
    setLoading(false);
    setStep(3);
  }, []);

  const submitPassword = useCallback(async () => {
    if (loadingRef.current) return;
    const errs = {};
    if (password.length < 8) errs.password = 'Минимум 8 символов';
    if (password !== password2 || !password2) errs.password2 = 'Пароли не совпадают';
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setErrors({});
    setLoading(true);
    await new Promise(r => setTimeout(r, 900));
    setLoading(false);
    setStep('done');
  }, [password, password2]);

  const resendOtp = useCallback(() => {
    setOtp(Array(6).fill(''));
    setErrors({});
    startTimer();
  }, [startTimer]);

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
