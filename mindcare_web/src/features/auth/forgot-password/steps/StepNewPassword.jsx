import styles from '../styles/forgot-password.module.css';
import PasswordStrength from '../components/PasswordStrength';

export default function StepNewPassword({
  password, setPassword, password2, setPassword2,
  errors, setErrors, loading, onSubmit, onBack,
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

  return (
    <div className={styles.panel}>
      <div>
        <h2 className={styles.heading}>
          Новый <span className={styles.headingEm}>пароль</span>
        </h2>
        <p className={styles.body} style={{ marginTop: 6 }}>
          Придумайте надёжный пароль для вашего аккаунта.
        </p>
      </div>

      <div className={styles.divider} />

      <div className={styles.field}>
        <label className={styles.label} htmlFor="fp-pass">
          Новый пароль
        </label>
        <input
          className={`${styles.input} ${errors.password ? styles.inputError : password ? styles.inputSuccess : ''}`}
          type="password"
          id="fp-pass"
          placeholder="Минимум 8 символов"
          autoComplete="new-password"
          value={password}
          onChange={handlePasswordChange}
          onBlur={handlePasswordBlur}
          aria-invalid={!!errors.password}
          aria-describedby="fp-pass-hint"
        />
        <PasswordStrength value={password} />
        <span
          id="fp-pass-hint"
          className={`${styles.hint} ${errors.password ? styles.hintError : styles.hintHidden}`}
          role="alert"
        >
          {errors.password || 'Минимум 8 символов'}
        </span>
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
          aria-invalid={!!errors.password2}
          aria-describedby="fp-pass2-hint"
        />
        <span
          id="fp-pass2-hint"
          className={`${styles.hint} ${errors.password2 ? styles.hintError : styles.hintHidden}`}
          role="alert"
        >
          {errors.password2 || 'Пароли не совпадают'}
        </span>
      </div>

      <button
        className={`${styles.btn} ${styles.btnPrimary} ${loading ? styles.btnLoading : ''}`}
        type="button"
        onClick={onSubmit}
        disabled={loading}
      >
        {loading ? <span className={styles.spinner} /> : 'Сохранить пароль'}
      </button>

      <div className={styles.aux}>
        <button className={`${styles.ghost} ${styles.ghostMuted}`} type="button" onClick={onBack}>
          ← Назад
        </button>
      </div>
    </div>
  );
}
