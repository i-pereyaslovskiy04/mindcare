import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import styles from './AuthModal.module.css';
import { useAuth } from '../AuthContext';
import { registerInit, registerConfirm } from '../../../api/auth.api';
import SocialButtons from './SocialButtons';
import RegistrationOtpStep, { EMPTY_CODE, useResendTimer } from './RegistrationOtpStep';
import Checkbox from '../../../components/UI/Checkbox/Checkbox';
import useAllowedEmailDomains from '../hooks/useAllowedEmailDomains';

const isEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);

const getPasswordStrength = (pass) => {
  if (!pass) return 0;
  let s = 0;
  if (pass.length >= 8) s++;
  if (/[A-Z]|[А-Я]/.test(pass)) s++;
  if (/[0-9]/.test(pass)) s++;
  if (/[^a-zA-Zа-яА-Я0-9]/.test(pass)) s++;
  return Math.min(s, 3);
};

const STRENGTH_LABELS = ['', 'Слабый', 'Средний', 'Надёжный'];
const STRENGTH_COLORS = ['', 'var(--strength-weak)', 'var(--strength-medium)', 'var(--strength-strong)'];
const STRENGTH_CLASSES = ['', 'w', 'm', 's'];

/**
 * onStepChange(step) — 'form' | 'code': AuthModal прячет вкладки
 * «Вход | Регистрация» на шаге подтверждения кода.
 */
export default function RegisterForm({ onSuccess, onStepChange }) {
  const { login } = useAuth();
  const navigate = useNavigate();

  // Step 1 — form fields
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [consent, setConsent] = useState(false);
  const [errors, setErrors] = useState({});
  const [passwordStrength, setPasswordStrength] = useState(0);

  // Step 2 — code confirmation
  const [step, setStep] = useState('form');
  const [otp, setOtp] = useState(EMPTY_CODE);
  const [otpError, setOtpError] = useState('');
  const [timer, restartTimer] = useResendTimer();

  // Shared
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState('');

  // Разрешённые домены — ТОЛЬКО из ответа backend (GET /api/public/email-domains),
  // подсказкой под полем Email. Допуск решает backend (init и confirm); список его
  // не заменяет и форму не блокирует. Тексты отказов приходят с backend как есть.
  const { data: allowedDomains, refetch: refetchDomains } = useAllowedEmailDomains();
  const domainsHint = allowedDomains.length
    ? `Разрешённые домены: ${allowedDomains.map((d) => `@${d}`).join(', ')}`
    : '';
  const emailDescribedBy = [
    errors.email ? 'r-email-hint' : null,
    domainsHint ? 'r-email-domains' : null,
  ].filter(Boolean).join(' ') || undefined;

  // Родитель узнаёт о шаге в том же обновлении, что и сама форма — без кадра,
  // где одновременно видны вкладки и шаг кода.
  const goToStep = (next) => {
    setStep(next);
    onStepChange?.(next);
  };

  // --- Step 1 validators ---
  const validateName = () => name.trim().length >= 2;
  const validateEmail = () => isEmail(email);
  const validatePassword = () => password.length >= 8;
  const validateConfirmPassword = () => confirmPassword === password && confirmPassword.length > 0;

  const handlePasswordChange = (e) => {
    const value = e.target.value;
    setPassword(value);
    setPasswordStrength(getPasswordStrength(value));
    if (confirmPassword) {
      setErrors((prev) => ({ ...prev, confirmPassword: confirmPassword !== value }));
    }
  };

  // --- Step 1 submit — send OTP ---
  const handleFormSubmit = async (e) => {
    e.preventDefault();
    setApiError('');

    const nameValid = validateName();
    const emailValid = validateEmail();
    const passwordValid = validatePassword();
    const confirmValid = validateConfirmPassword();

    setErrors({
      name: !nameValid,
      email: !emailValid,
      password: !passwordValid,
      confirmPassword: !confirmValid,
      consent: !consent,
    });

    if (!nameValid || !emailValid || !passwordValid || !confirmValid || !consent) return;

    setIsLoading(true);
    try {
      await registerInit({ name: name.trim(), email, password });
      setOtp(EMPTY_CODE);
      setOtpError('');
      restartTimer();
      goToStep('code');
    } catch (err) {
      setApiError(err.message || 'Ошибка. Попробуйте снова.');
      // Отказ 422 мог означать, что список доменов изменился, — перечитываем,
      // чтобы подсказка не расходилась с текстом ошибки.
      if (err.status === 422) refetchDomains();
    } finally {
      setIsLoading(false);
    }
  };

  // --- Step 2 submit — confirm OTP (авто-подтверждение — в RegistrationOtpStep) ---
  const handleConfirm = useCallback(async (digits) => {
    const code = digits.join('');
    if (code.length < 6) return;
    setOtpError('');
    setIsLoading(true);
    try {
      await registerConfirm({ email, code });
      await login({ email, password });
      onSuccess();
      navigate('/dashboard');
    } catch (err) {
      setOtpError(err.message || 'Неверный код. Попробуйте снова.');
      setOtp(EMPTY_CODE);
      // Домен могли отключить между init и confirm — обновляем подсказку.
      if (err.status === 422) refetchDomains();
    } finally {
      setIsLoading(false);
    }
  }, [email, password, login, navigate, onSuccess, refetchDomains]);

  // --- Resend ---
  const handleResend = async () => {
    setApiError('');
    setOtpError('');
    setIsLoading(true);
    try {
      await registerInit({ name: name.trim(), email, password });
      setOtp(EMPTY_CODE);
      restartTimer();
    } catch (err) {
      setOtpError(err.message || 'Не удалось отправить код. Попробуйте позже.');
      if (err.status === 422) refetchDomains();
    } finally {
      setIsLoading(false);
    }
  };

  // ── STEP 2: код подтверждения (общий шаг, без вкладок) ─────────────────────
  if (step === 'code') {
    return (
      <RegistrationOtpStep
        email={email}
        code={otp}
        onCodeChange={(next) => { setOtp(next); setOtpError(''); }}
        error={otpError}
        timer={timer}
        onResend={handleResend}
        onConfirm={handleConfirm}
        loading={isLoading}
        backLabel="← Изменить данные"
        onBack={() => { goToStep('form'); setApiError(''); }}
      />
    );
  }

  // ── STEP 1: форма регистрации ──────────────────────────────────────────────
  return (
    <form className={`${styles.authPanel} ${styles.active}`} onSubmit={handleFormSubmit} noValidate>
      {/* VK (заглушка) + Яндекс — та же логика, что на соседней вкладке. */}
      <SocialButtons />

      <div className={`${styles.authField} ${errors.name ? styles.hasErr : ''}`}>
        <label htmlFor="r-name">Имя</label>
        <input
          type="text"
          id="r-name"
          placeholder="Ваше имя"
          autoComplete="given-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => setErrors((p) => ({ ...p, name: !validateName() }))}
          className={errors.name ? styles.err : name && validateName() ? styles.ok : ''}
          aria-invalid={errors.name ? 'true' : undefined}
          aria-describedby={errors.name ? 'r-name-hint' : undefined}
        />
        <span className={styles.authHint} id="r-name-hint" role="alert">
          Введите имя (минимум 2 символа)
        </span>
      </div>

      <div className={`${styles.authField} ${errors.email ? styles.hasErr : ''}`}>
        <label htmlFor="r-email">Email</label>
        <input
          type="email"
          id="r-email"
          placeholder="Введите email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onBlur={() => setErrors((p) => ({ ...p, email: !validateEmail() }))}
          className={errors.email ? styles.err : email && isEmail(email) ? styles.ok : ''}
          aria-invalid={errors.email ? 'true' : undefined}
          aria-describedby={emailDescribedBy}
        />
        <span className={styles.authHint} id="r-email-hint" role="alert">
          Введите корректный email
        </span>
        {domainsHint && (
          <span className={styles.authNote} id="r-email-domains">
            {domainsHint}
          </span>
        )}
      </div>

      <div className={`${styles.authField} ${errors.password ? styles.hasErr : ''}`}>
        <label htmlFor="r-pass">Пароль</label>
        <input
          type="password"
          id="r-pass"
          placeholder="Минимум 8 символов"
          autoComplete="new-password"
          value={password}
          onChange={handlePasswordChange}
          onBlur={() => setErrors((p) => ({ ...p, password: !validatePassword() }))}
          className={errors.password ? styles.err : password && validatePassword() ? styles.ok : ''}
          aria-invalid={errors.password ? 'true' : undefined}
          aria-describedby="r-pass-hint r-pass-strength"
        />
        <div className={styles.psBars} aria-hidden="true">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className={`${styles.psBar} ${
                i <= passwordStrength ? styles[STRENGTH_CLASSES[passwordStrength]] : ''
              }`}
            />
          ))}
        </div>
        <div
          id="r-pass-strength"
          className={styles.psLbl}
          style={{ color: STRENGTH_COLORS[passwordStrength] }}
          aria-live="polite"
        >
          {STRENGTH_LABELS[passwordStrength]}
        </div>
        <span className={styles.authHint} id="r-pass-hint" role="alert">
          Минимум 8 символов
        </span>
      </div>

      <div className={`${styles.authField} ${errors.confirmPassword ? styles.hasErr : ''}`}>
        <label htmlFor="r-pass2">Повторите пароль</label>
        <input
          type="password"
          id="r-pass2"
          placeholder="Повторите пароль"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          onBlur={() => setErrors((p) => ({ ...p, confirmPassword: !validateConfirmPassword() }))}
          className={
            errors.confirmPassword
              ? styles.err
              : confirmPassword && validateConfirmPassword()
              ? styles.ok
              : ''
          }
          aria-invalid={errors.confirmPassword ? 'true' : undefined}
          aria-describedby={errors.confirmPassword ? 'r-pass2-hint' : undefined}
        />
        <span className={styles.authHint} id="r-pass2-hint" role="alert">
          Пароли не совпадают
        </span>
      </div>

      <Checkbox
        id="r-consent"
        checked={consent}
        onChange={(val) => {
          setConsent(val);
          setErrors((p) => ({ ...p, consent: !val }));
        }}
        label={
          <>
            Согласен(на) с{' '}
            {/* Новая вкладка: переход в этой же вкладке выгружает страницу и
                стирает заполненную форму регистрации. */}
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
        error={errors.consent}
        ariaDescribedBy={errors.consent ? 'r-consent-hint' : undefined}
      />
      {errors.consent && (
        <span className={styles.consentHint} id="r-consent-hint" role="alert">
          Необходимо принять политику персональных данных
        </span>
      )}

      {apiError && (
        <div className={styles.apiError} role="alert">{apiError}</div>
      )}

      <button type="submit" className={styles.authBtn} disabled={isLoading}>
        {isLoading ? 'Отправляем код…' : 'Продолжить'}
      </button>
    </form>
  );
}
