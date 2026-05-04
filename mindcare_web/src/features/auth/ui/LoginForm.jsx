import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import styles from './AuthModal.module.css';
import { useAuth } from '../AuthContext';
import { getRoleHome } from '../authUtils';
import { TelegramIcon, VKIcon, YandexIcon } from '../../../components/icons';

const isEmail = (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);

export default function LoginForm({ onSuccess, onForgotPassword }) {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState('');

  const validateEmail = () => isEmail(email);
  const validatePassword = () => password.length > 0;

  const handleEmailBlur = () =>
    setErrors((prev) => ({ ...prev, email: !validateEmail() }));

  const handlePasswordBlur = () =>
    setErrors((prev) => ({ ...prev, password: !validatePassword() }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setApiError('');

    const emailValid = validateEmail();
    const passwordValid = validatePassword();
    setErrors({ email: !emailValid, password: !passwordValid });
    if (!emailValid || !passwordValid) return;

    setIsLoading(true);
    try {
      const role = await login({ email, password });
      onSuccess();
      navigate(getRoleHome(role));
    } catch (err) {
      setApiError(err.message || 'Ошибка входа. Попробуйте снова.');
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

      <div className={`${styles.authField} ${errors.email ? styles.hasErr : ''}`}>
        <label htmlFor="l-email">Email</label>
        <input
          type="email"
          id="l-email"
          placeholder="example@donnu.ru"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onBlur={handleEmailBlur}
          className={errors.email ? styles.err : email && validateEmail() ? styles.ok : ''}
          aria-invalid={errors.email ? 'true' : undefined}
          aria-describedby={errors.email ? 'l-email-hint' : undefined}
        />
        <span className={styles.authHint} id="l-email-hint" role="alert">
          Введите корректный email
        </span>
      </div>

      <div className={`${styles.authField} ${errors.password ? styles.hasErr : ''}`}>
        <label htmlFor="l-pass">Пароль</label>
        <input
          type="password"
          id="l-pass"
          placeholder="Ваш пароль"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onBlur={handlePasswordBlur}
          className={errors.password ? styles.err : password ? styles.ok : ''}
          aria-invalid={errors.password ? 'true' : undefined}
          aria-describedby={errors.password ? 'l-pass-hint' : undefined}
        />
        <span className={styles.authHint} id="l-pass-hint" role="alert">
          Пароль не может быть пустым
        </span>
      </div>

      {apiError && (
        <div className={styles.apiError} role="alert">{apiError}</div>
      )}

      <div className={styles.authForgot}>
        <button type="button" className={styles.authForgotBtn} onClick={onForgotPassword}>
          Забыли пароль?
        </button>
      </div>

      <button type="submit" className={styles.authBtn} disabled={isLoading}>
        {isLoading ? 'Входим…' : 'Войти'}
      </button>
    </form>
  );
}
