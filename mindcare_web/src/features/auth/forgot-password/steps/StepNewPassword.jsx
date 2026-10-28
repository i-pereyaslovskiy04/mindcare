import styles from '../styles/forgot-password.module.css';
import PasswordStrength from '../components/PasswordStrength';

const PASS_ERROR_ID = 'fp-pass-error';
const PASS2_ERROR_ID = 'fp-pass2-error';

/**
 * Шаг 3: новый пароль. Форма — Enter в поле отправляет только этот шаг.
 * fieldRef — поле «Новый пароль» (фокус при открытии шага); ошибка проверки
 * переводит фокус на первое ошибочное поле.
 * email — для скрытого поля username: менеджер паролей сохраняет пароль
 * к нужному аккаунту.
 */
export default function StepNewPassword({
  email, password, setPassword, password2, setPassword2,
  errors, setErrors, loading, onSubmit, onBack, fieldRef,
}) {
  const handlePasswordChange = (e) => {
    setPassword(e.target.value);
    if (errors.password) setErrors(prev => ({ ...prev, password: null }));
  };

  const handlePassword2Change = (e) => {
    setPassword2(e.target.value);
    if (errors.password2) setErrors(prev => ({ ...prev, password2: null }));
  };

  const handlePasswordBlur = () => {
    if (password && password.length < 8) {
      setErrors(prev => ({ ...prev, password: 'Минимум 8 символов' }));
    }
  };

  const handlePassword2Blur = () => {
    if (password2 && password2 !== password) {
      setErrors(prev => ({ ...prev, password2: 'Пароли не совпадают' }));
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const invalid = await onSubmit();
    if (invalid === 'password') fieldRef?.current?.focus();
    else if (invalid === 'password2') document.getElementById('fp-pass2')?.focus();
  };

  return (
    <form className={styles.panel} onSubmit={handleSubmit} noValidate>
      <div>
        <h2 className={styles.heading}>
          Новый <span className={styles.headingEm}>пароль</span>
        </h2>
        <p className={styles.lead}>
          Придумайте надёжный пароль для вашего аккаунта.
        </p>
      </div>

      {/* Для менеджера паролей: аккаунт, к которому относится новый пароль. */}
      <input type="email" name="username" autoComplete="username" value={email} readOnly hidden />

      <div className={styles.fields}>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="fp-pass">
            Новый пароль
          </label>
          <input
            ref={fieldRef}
            className={`${styles.input} ${errors.password ? styles.inputError : password ? styles.inputSuccess : ''}`}
            type="password"
            id="fp-pass"
            placeholder="Минимум 8 символов"
            autoComplete="new-password"
            value={password}
            onChange={handlePasswordChange}
            onBlur={handlePasswordBlur}
            aria-invalid={errors.password ? 'true' : undefined}
            aria-describedby={errors.password ? PASS_ERROR_ID : undefined}
          />
          <PasswordStrength value={password} />
          {errors.password && (
            <span id={PASS_ERROR_ID} className={styles.hint} role="alert">{errors.password}</span>
          )}
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="fp-pass2">
            Повторите пароль
          </label>
          <input
            className={`${styles.input} ${errors.password2 ? styles.inputError : password2 && password2 === password ? styles.inputSuccess : ''}`}
            type="password"
            id="fp-pass2"
            placeholder="Повторите пароль"
            autoComplete="new-password"
            value={password2}
            onChange={handlePassword2Change}
            onBlur={handlePassword2Blur}
            aria-invalid={errors.password2 ? 'true' : undefined}
            aria-describedby={errors.password2 ? PASS2_ERROR_ID : undefined}
          />
          {errors.password2 && (
            <span id={PASS2_ERROR_ID} className={styles.hint} role="alert">{errors.password2}</span>
          )}
        </div>
      </div>

      <div className={styles.actions}>
        <button
          className={`${styles.btn} ${styles.btnPrimary} ${loading ? styles.btnLoading : ''}`}
          type="submit"
          disabled={loading}
        >
          {loading ? <span className={styles.spinner} /> : 'Сохранить пароль'}
        </button>
        <button className={`${styles.ghost} ${styles.ghostMuted}`} type="button" onClick={onBack}>
          ← Изменить код
        </button>
      </div>
    </form>
  );
}
