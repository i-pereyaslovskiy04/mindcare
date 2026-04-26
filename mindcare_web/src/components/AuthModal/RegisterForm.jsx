import { useState } from 'react';
import styles from './AuthModal.module.css';
import { register } from '../../services/api';
import { TelegramIcon, VKIcon, YandexIcon } from '../icons';

const isEmail = (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);

// Returns 0–3. Fixed: uppercase check was incorrectly matching cyrillic lowercase.
const getPasswordStrength = (pass) => {
  if (!pass) return 0;
  let s = 0;
  if (pass.length >= 8) s++;
  if (/[A-Z]|[А-Я]/.test(pass)) s++;   // uppercase only
  if (/[0-9]/.test(pass)) s++;
  if (/[^a-zA-Zа-яА-Я0-9]/.test(pass)) s++;
  return Math.min(s, 3);
};

const STRENGTH_LABELS = ['', 'Слабый', 'Средний', 'Надёжный'];
const STRENGTH_COLORS = ['', '#C0392B', '#D4891A', '#5D8A5E'];
const STRENGTH_CLASSES = ['', 'w', 'm', 's'];

export default function RegisterForm({ onSuccess }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [consent, setConsent] = useState(false);
  const [errors, setErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState('');
  const [passwordStrength, setPasswordStrength] = useState(0);

  const validateName = () => name.trim().length >= 2;
  const validateEmail = () => isEmail(email);
  const validatePassword = () => password.length >= 8;
  const validateConfirmPassword = () =>
    confirmPassword === password && confirmPassword.length > 0;

  const handlePasswordChange = (e) => {
    const value = e.target.value;
    setPassword(value);
    setPasswordStrength(getPasswordStrength(value));
    // Re-validate confirmPassword live if already touched.
    if (confirmPassword) {
      setErrors((prev) => ({ ...prev, confirmPassword: confirmPassword !== value }));
    }
  };

  const handleNameBlur = () =>
    setErrors((prev) => ({ ...prev, name: !validateName() }));
  const handleEmailBlur = () =>
    setErrors((prev) => ({ ...prev, email: !validateEmail() }));
  const handlePasswordBlur = () =>
    setErrors((prev) => ({ ...prev, password: !validatePassword() }));
  const handleConfirmPasswordBlur = () =>
    setErrors((prev) => ({ ...prev, confirmPassword: !validateConfirmPassword() }));

  const handleConsentChange = (e) => {
    setConsent(e.target.checked);
    setErrors((prev) => ({ ...prev, consent: !e.target.checked }));
  };

  const handleSubmit = async (e) => {
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
      await register({ name, email, password });
      onSuccess();
    } catch (err) {
      setApiError(err.message || 'Ошибка регистрации. Попробуйте снова.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form className={`${styles.authPanel} ${styles.active}`} onSubmit={handleSubmit} noValidate>
      <div className={styles.socialSection}>
        <div className={styles.socialLabel}>Быстрая авторизация</div>
        <div className={styles.socialBtns}>
          <button type="button" className={styles.socBtn} aria-label="Войти через Telegram">
            <div className={styles.socBtnIcon}>
              <TelegramIcon />
            </div>
            <span className={styles.socBtnLabel}>Telegram</span>
          </button>
          <button type="button" className={styles.socBtn} aria-label="Войти через ВКонтакте">
            <div className={styles.socBtnIcon}>
              <VKIcon />
            </div>
            <span className={styles.socBtnLabel}>VK</span>
          </button>
          <button type="button" className={styles.socBtn} aria-label="Войти через Яндекс">
            <div className={styles.socBtnIcon}>
              <YandexIcon />
            </div>
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
          onBlur={handleNameBlur}
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
          onBlur={handleEmailBlur}
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
          onBlur={handlePasswordBlur}
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
          onBlur={handleConfirmPasswordBlur}
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
          onChange={handleConsentChange}
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
        <div className={styles.apiError} role="alert">
          {apiError}
        </div>
      )}

      <button type="submit" className={styles.authBtn} disabled={isLoading}>
        {isLoading ? 'Создаём аккаунт…' : 'Создать аккаунт'}
      </button>
    </form>
  );
}
