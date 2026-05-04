import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import styles from './AuthModal.module.css';
import { authApi, useAuth } from '../AuthContext';
import { getRoleHome } from '../authUtils';
import { TelegramIcon, VKIcon, YandexIcon } from '../../../components/icons';
import CodeInput from '../../../components/CodeInput/CodeInput';

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
const STRENGTH_COLORS = ['', '#C0392B', '#D4891A', '#5D8A5E'];
const STRENGTH_CLASSES = ['', 'w', 'm', 's'];
const RESEND_COOLDOWN = 60;

export default function RegisterForm({ onSuccess }) {
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
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [otpError, setOtpError] = useState('');
  const [timer, setTimer] = useState(0);

  // Shared
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState('');

  // --- Timer countdown ---
  useEffect(() => {
    if (timer <= 0) return;
    const id = setTimeout(() => setTimer((t) => t - 1), 1000);
    return () => clearTimeout(id);
  }, [timer]);

  // --- Auto-submit when all 6 digits filled ---
  useEffect(() => {
    if (step !== 'code') return;
    if (!otp.every((d) => d !== '')) return;
    const id = setTimeout(() => handleConfirm(otp), 120);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [otp, step]);

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
      await authApi.registerInit({ name: name.trim(), email, password });
      setOtp(['', '', '', '', '', '']);
      setOtpError('');
      setTimer(RESEND_COOLDOWN);
      setStep('code');
    } catch (err) {
      setApiError(err.message || 'Ошибка. Попробуйте снова.');
    } finally {
      setIsLoading(false);
    }
  };

  // --- Step 2 submit — confirm OTP ---
  const handleConfirm = useCallback(async (digits) => {
    const code = digits.join('');
    if (code.length < 6) return;
    setOtpError('');
    setIsLoading(true);
    try {
      await authApi.registerConfirm({ email, code });
      const role = await login({ email, password });
      onSuccess();
      navigate(getRoleHome(role));
    } catch (err) {
      setOtpError(err.message || 'Неверный код. Попробуйте снова.');
      setOtp(['', '', '', '', '', '']);
    } finally {
      setIsLoading(false);
    }
  }, [email, password, login, navigate, onSuccess]);

  // --- Resend ---
  const handleResend = async () => {
    setApiError('');
    setOtpError('');
    setIsLoading(true);
    try {
      await authApi.registerInit({ name: name.trim(), email, password });
      setOtp(['', '', '', '', '', '']);
      setTimer(RESEND_COOLDOWN);
    } catch (err) {
      setOtpError(err.message || 'Не удалось отправить код. Попробуйте позже.');
    } finally {
      setIsLoading(false);
    }
  };

  // ── STEP 2: код подтверждения ──────────────────────────────────────────────
  if (step === 'code') {
    return (
      <div className={`${styles.authPanel} ${styles.active}`}>
        <p className={styles.stepDesc}>
          Отправили 6-значный код на{' '}
          <strong className={styles.stepDescStrong}>{email}</strong>
        </p>

        <CodeInput
          value={otp}
          onChange={(next) => { setOtp(next); setOtpError(''); }}
          error={!!otpError}
        />

        {otpError && (
          <div className={styles.apiError} role="alert">{otpError}</div>
        )}

        {timer > 0 ? (
          <p className={styles.otpTimer}>
            Отправить повторно через{' '}
            <span className={styles.otpTimerCount}>{timer}</span> с
          </p>
        ) : (
          <div className={styles.otpAux}>
            <button
              type="button"
              className={styles.ghost}
              onClick={handleResend}
              disabled={isLoading}
            >
              Отправить повторно
            </button>
          </div>
        )}

        <button
          type="button"
          className={styles.authBtn}
          onClick={() => handleConfirm(otp)}
          disabled={isLoading || otp.some((d) => d === '')}
        >
          {isLoading ? 'Проверяем…' : 'Подтвердить'}
        </button>

        <div className={styles.otpAux}>
          <button
            type="button"
            className={`${styles.ghost} ${styles.ghostMuted}`}
            onClick={() => { setStep('form'); setApiError(''); }}
          >
            ← Изменить данные
          </button>
        </div>
      </div>
    );
  }

  // ── STEP 1: форма регистрации ──────────────────────────────────────────────
  return (
    <form className={`${styles.authPanel} ${styles.active}`} onSubmit={handleFormSubmit} noValidate>
      <div className={styles.socialSection}>
        <div className={styles.socialLabel}>Быстрая авторизация</div>
        <div className={styles.socialBtns}>
          <button type="button" className={styles.socBtn} aria-label="Войти через Telegram">
            <div className={styles.socBtnIcon}><TelegramIcon /></div>
            <span className={styles.socBtnLabel}>Telegram</span>
          </button>
          <button type="button" className={styles.socBtn} aria-label="Войти через ВКонтакте">
            <div className={styles.socBtnIcon}><VKIcon /></div>
            <span className={styles.socBtnLabel}>VK</span>
          </button>
          <button type="button" className={styles.socBtn} aria-label="Войти через Яндекс">
            <div className={styles.socBtnIcon}><YandexIcon /></div>
            <span className={styles.socBtnLabel}>Яндекс</span>
          </button>
        </div>
      </div>

      <div className={styles.authDivider}>
        <div className={styles.authDividerLine} />
        <span className={styles.authDividerText}>или продолжить с email</span>
        <div className={styles.authDividerLine} />
      </div>

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
          placeholder="example@donnu.ru"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onBlur={() => setErrors((p) => ({ ...p, email: !validateEmail() }))}
          className={errors.email ? styles.err : email && isEmail(email) ? styles.ok : ''}
          aria-invalid={errors.email ? 'true' : undefined}
          aria-describedby={errors.email ? 'r-email-hint' : undefined}
        />
        <span className={styles.authHint} id="r-email-hint" role="alert">
          Введите корректный email
        </span>
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

      <div className={`${styles.consentRow} ${errors.consent ? styles.consentErr : ''}`}>
        <input
          type="checkbox"
          className={styles.consentCheck}
          id="r-consent"
          checked={consent}
          onChange={(e) => {
            setConsent(e.target.checked);
            setErrors((p) => ({ ...p, consent: !e.target.checked }));
          }}
          aria-describedby={errors.consent ? 'r-consent-hint' : undefined}
        />
        <label className={styles.consentText} htmlFor="r-consent">
          Согласен(на) с{' '}
          <a href="/privacy-policy">политикой персональных данных</a>
        </label>
      </div>
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
