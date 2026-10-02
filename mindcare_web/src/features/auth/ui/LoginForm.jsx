import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import styles from './AuthModal.module.css';
import { useAuth } from '../AuthContext';
import { YandexIcon } from '../../../components/icons';
import { oauthStart } from '../../../api/auth.api';
import { getPublicConfig, socialProvidersOf } from '../../../api/config.api';
import {
  isSafeAuthorizeUrl,
  navigateToProvider,
  startErrorMessage,
} from '../lib/oauthCallback';

const isEmail = (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);

const AUTH_ERRORS_RU = {
  'Invalid email or password':   'Неверный email или пароль',
  'Invalid or expired session':  'Сессия истекла. Войдите снова.',
  'Not authenticated':           'Необходимо войти в аккаунт',
  'Insufficient permissions':    'Недостаточно прав',
  'User not found':              'Пользователь не найден',
};
const toRu = (msg) => AUTH_ERRORS_RU[msg] ?? msg;

export default function LoginForm({ onSuccess, onForgotPassword }) {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState('');
  // Провайдеры, реально зарегистрированные backend'ом (GET /api/public/config).
  // Пока список не получен или запрос упал — социального входа нет вовсе,
  // вход по email и паролю работает как обычно.
  const [socialProviders, setSocialProviders] = useState([]);
  const [socialLoading, setSocialLoading] = useState(false);
  const [socialError, setSocialError] = useState('');

  useEffect(() => {
    let cancelled = false;
    getPublicConfig()
      .then((config) => {
        if (!cancelled) setSocialProviders(socialProvidersOf(config));
      })
      .catch(() => {
        if (!cancelled) setSocialProviders([]);
      });
    return () => { cancelled = true; };
  }, []);

  const yandexAvailable = socialProviders.includes('yandex');

  const handleYandexLogin = async () => {
    if (socialLoading) return;
    setSocialError('');
    setSocialLoading(true);
    try {
      const data = await oauthStart('yandex');
      const url = data?.authorize_url;
      if (!isSafeAuthorizeUrl(url)) throw new Error('invalid authorize_url');
      // Top-level переход на страницу Яндекса; state привязан HttpOnly-cookie,
      // поэтому ни адрес, ни state нигде на клиенте не сохраняются.
      navigateToProvider(url);
    } catch (err) {
      setSocialError(startErrorMessage(err));
      setSocialLoading(false);
    }
  };

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
      await login({ email, password });
      onSuccess();
      // Кабинет выбирает DashboardRedirect (multi-role: chooser/activeRole).
      navigate('/dashboard');
    } catch (err) {
      setApiError(toRu(err.message) || 'Ошибка входа. Попробуйте снова.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form className={`${styles.authPanel} ${styles.active}`} onSubmit={handleSubmit} noValidate>
      {yandexAvailable && (
        <>
          <div className={styles.socialSection}>
            <div className={styles.socialLabel}>Быстрая авторизация</div>
            <div className={styles.socialBtns}>
              <button
                type="button"
                className={styles.socBtn}
                aria-label="Войти через Яндекс"
                onClick={handleYandexLogin}
                disabled={socialLoading}
                aria-busy={socialLoading ? 'true' : undefined}
              >
                <div className={styles.socBtnIcon} aria-hidden="true"><YandexIcon /></div>
                <span className={styles.socBtnLabel}>
                  {socialLoading ? 'Переход…' : 'Яндекс'}
                </span>
              </button>
            </div>
            {socialError && (
              <div className={styles.apiError} role="alert">{socialError}</div>
            )}
          </div>

          <div className={styles.authDivider}>
            <div className={styles.authDividerLine} />
            <span className={styles.authDividerText}>или продолжить с email</span>
            <div className={styles.authDividerLine} />
          </div>
        </>
      )}

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
