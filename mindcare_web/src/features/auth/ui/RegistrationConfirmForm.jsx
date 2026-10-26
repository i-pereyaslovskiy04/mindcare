import { useState } from 'react';
import styles from './AuthModal.module.css';
import CodeInput from '../../../components/CodeInput/CodeInput';
import { registerConfirm } from '../../../api/auth.api';
import { EMPTY_CODE } from './RegistrationOtpStep';

const isEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);

export const CONFIRM_FALLBACK_ERROR = 'Не удалось подтвердить регистрацию. Попробуйте снова.';

/**
 * «Подтверждение регистрации» без исходной вкладки: пользователь пришёл по
 * кнопке «Продолжить регистрацию» из письма (/register/confirm) или после
 * перезагрузки и вводит email и код сам. Тот же POST /api/auth/register/confirm,
 * что у обычного шага кода (backend подтверждает по email + код).
 *
 * Пароль здесь неизвестен, поэтому автоматического входа нет: onConfirmed(email)
 * — владелец показывает вход с сообщением. Email и код живут только в state
 * этой формы: не в URL, не в localStorage/sessionStorage.
 *
 * onRestart — «Начать регистрацию заново» (обычная форма регистрации): новый
 * код можно получить только через неё, register/init требует имя и пароль.
 */
export default function RegistrationConfirmForm({ onConfirmed, onRestart }) {
  const [email, setEmail] = useState('');
  const [code, setCode] = useState(EMPTY_CODE);
  const [emailError, setEmailError] = useState(false);
  const [codeError, setCodeError] = useState(false);
  const [apiError, setApiError] = useState('');
  const [loading, setLoading] = useState(false);

  const codeComplete = code.every((d) => d !== '');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setApiError('');
    const emailOk = isEmail(email.trim());
    setEmailError(!emailOk);
    setCodeError(!codeComplete);
    if (!emailOk || !codeComplete) return;

    setLoading(true);
    try {
      const confirmedEmail = email.trim();
      await registerConfirm({ email: confirmedEmail, code: code.join('') });
      onConfirmed(confirmedEmail);
    } catch (err) {
      const m = err?.message;
      setApiError(typeof m === 'string' && m && !/^HTTP \d+$/.test(m) ? m : CONFIRM_FALLBACK_ERROR);
      setCode(EMPTY_CODE);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className={`${styles.authPanel} ${styles.active}`} onSubmit={handleSubmit} noValidate>
      <h2 className={styles.stepTitle}>Подтверждение регистрации</h2>
      <p className={styles.stepDesc}>
        Введите email, который указали при регистрации, и код из письма.
      </p>

      <div className={`${styles.authField} ${emailError ? styles.hasErr : ''}`}>
        <label htmlFor="rc-email">Email</label>
        <input
          type="email"
          id="rc-email"
          placeholder="Введите email"
          autoComplete="email"
          value={email}
          onChange={(e) => { setEmail(e.target.value); setApiError(''); }}
          onBlur={() => setEmailError(Boolean(email) && !isEmail(email.trim()))}
          className={emailError ? styles.err : email && isEmail(email.trim()) ? styles.ok : ''}
          aria-invalid={emailError ? 'true' : undefined}
          aria-describedby={emailError ? 'rc-email-hint' : undefined}
        />
        <span className={styles.authHint} id="rc-email-hint" role="alert">
          Введите корректный email
        </span>
      </div>

      <div className={`${styles.authField} ${codeError ? styles.hasErr : ''}`}>
        {/* Видимая подпись; доступное имя у группы цифр CodeInput — то же. */}
        <span className={styles.fieldLabel} aria-hidden="true">Код подтверждения</span>
        <CodeInput
          value={code}
          onChange={(next) => { setCode(next); setCodeError(false); setApiError(''); }}
          error={codeError || Boolean(apiError)}
        />
        <span className={styles.authHint} id="rc-code-hint" role="alert">
          Введите 6 цифр из письма
        </span>
      </div>

      {apiError && (
        <div className={styles.apiError} role="alert">{apiError}</div>
      )}

      <button type="submit" className={styles.authBtn} disabled={loading}>
        {loading ? 'Проверяем…' : 'Подтвердить регистрацию'}
      </button>

      <p className={styles.stepDesc}>
        Код истёк или письмо не пришло? Заполните форму регистрации ещё раз.
      </p>
      <div className={styles.otpAux}>
        <button type="button" className={styles.ghost} onClick={onRestart} disabled={loading}>
          Начать регистрацию заново
        </button>
      </div>
    </form>
  );
}
