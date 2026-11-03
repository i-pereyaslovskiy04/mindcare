import styles from '../styles/forgot-password.module.css';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const ERROR_ID = 'fp-email-error';

/**
 * Шаг 1: email. Форма — Enter в поле отправляет только этот шаг.
 * fieldRef — поле email (фокус при открытии шага и после ошибки проверки).
 * onSubmit() возвращает имя поля при ошибке клиентской проверки.
 */
export default function StepEmail({
  email, setEmail, errors, setErrors, loading, onSubmit, readOnly = false, fieldRef,
}) {
  const handleChange = (e) => {
    setEmail(e.target.value);
    if (errors.email) setErrors(prev => ({ ...prev, email: null }));
  };

  const handleBlur = () => {
    if (email && !EMAIL_RE.test(email.trim())) {
      setErrors(prev => ({ ...prev, email: 'Введите корректный email' }));
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (await onSubmit()) fieldRef?.current?.focus();
  };

  return (
    <form className={styles.panel} onSubmit={handleSubmit} noValidate>
      <div>
        <h2 className={styles.heading}>
          Восстановление <span className={styles.headingEm}>пароля</span>
        </h2>
        <p className={styles.lead}>
          Введите почту, указанную при регистрации. Мы пришлём код подтверждения.
        </p>
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="fp-email">
          Электронная почта
        </label>
        <input
          ref={fieldRef}
          className={`${styles.input} ${errors.email ? styles.inputError : ''}`}
          type="email"
          id="fp-email"
          placeholder="Введите email"
          autoComplete="email"
          value={email}
          onChange={handleChange}
          onBlur={handleBlur}
          readOnly={readOnly}
          aria-invalid={errors.email ? 'true' : undefined}
          aria-describedby={errors.email ? ERROR_ID : undefined}
        />
        {errors.email && (
          <span id={ERROR_ID} className={styles.hint} role="alert">{errors.email}</span>
        )}
      </div>

      <button
        className={`${styles.btn} ${styles.btnPrimary} ${loading ? styles.btnLoading : ''}`}
        type="submit"
        disabled={loading}
      >
        {loading ? <span className={styles.spinner} /> : 'Отправить код'}
      </button>
    </form>
  );
}
