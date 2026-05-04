import styles from '../styles/forgot-password.module.css';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function StepEmail({ email, setEmail, errors, setErrors, loading, onSubmit }) {
  const handleChange = (e) => {
    setEmail(e.target.value);
    if (errors.email) setErrors(prev => ({ ...prev, email: null }));
  };

  const handleBlur = () => {
    if (email && !EMAIL_RE.test(email.trim())) {
      setErrors(prev => ({ ...prev, email: 'Введите корректный email' }));
    }
  };

  return (
    <div className={styles.panel}>
      <div>
        <h1 className={styles.heading}>
          Восстановление<br /><span className={styles.headingEm}>пароля</span>
        </h1>
        <p className={styles.body} style={{ marginTop: 6 }}>
          Введите почту, указанную при регистрации. Мы пришлём код подтверждения.
        </p>
      </div>

      <div className={styles.divider} />

      <div className={styles.field}>
        <label className={styles.label} htmlFor="fp-email">
          Электронная почта
        </label>
        <input
          className={`${styles.input} ${errors.email ? styles.inputError : ''}`}
          type="email"
          id="fp-email"
          placeholder="example@donnu.ru"
          autoComplete="email"
          value={email}
          onChange={handleChange}
          onBlur={handleBlur}
          aria-invalid={!!errors.email}
          aria-describedby="fp-email-hint"
        />
        <span
          id="fp-email-hint"
          className={`${styles.hint} ${errors.email ? styles.hintError : styles.hintHidden}`}
          role="alert"
        >
          {errors.email || 'Введите почту, привязанную к аккаунту'}
        </span>
      </div>

      <button
        className={`${styles.btn} ${styles.btnPrimary} ${loading ? styles.btnLoading : ''}`}
        type="button"
        onClick={onSubmit}
        disabled={loading}
      >
        {loading ? <span className={styles.spinner} /> : 'Отправить код'}
      </button>
    </div>
  );
}
