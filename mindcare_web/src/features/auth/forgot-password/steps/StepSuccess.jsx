import styles from '../styles/forgot-password.module.css';

export default function StepSuccess({ onClose }) {
  return (
    <div className={styles.panel}>
      <div className={styles.successIcon} aria-hidden="true">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
          <path
            d="M5 12l5 5 9-9"
            stroke="#5D8A5E"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>

      <div>
        <h2 className={`${styles.heading} ${styles.headingCenter}`}>
          Пароль<br /><span className={styles.headingEm}>изменён</span>
        </h2>
        <p className={`${styles.body} ${styles.bodyCenter}`} style={{ marginTop: 6 }}>
          Теперь вы можете войти в аккаунт с новым паролем.
        </p>
      </div>

      <div className={styles.divider} />

      <button className={`${styles.btn} ${styles.btnSuccess}`} type="button" onClick={onClose}>
        Войти в аккаунт
      </button>
    </div>
  );
}
