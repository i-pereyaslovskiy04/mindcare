import { useState } from 'react';
import styles from './AuthModal.module.css';

const isEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);

/**
 * Шаг «Почта для регистрации» при регистрации через провайдера, у которого
 * email выбирает пользователь (VK ID, Stage Social Auth VK-1B). Шаг ВНУТРИ
 * AuthModal (его монтирует SocialRegistrationFlow) — не страница и не
 * отдельная карточка: после него идёт общий RegistrationOtpStep.
 *
 * Оформление — только общие классы AuthModal.module.css (те же, что у форм
 * входа, регистрации и шага кода). Своей типографики и своих размеров у шага
 * нет; шрифт наследуется от модалки.
 *
 * Два вида:
 *   • адрес — maskedEmail есть и emailAllowed: поле только для чтения с
 *     МАСКИРОВАННЫМ адресом, «Продолжить» и «Нет доступа к этой почте?
 *     Указать другую»;
 *   • ввод — адреса нет, он не подходит (домен вне разрешённых) или
 *     пользователь сам выбрал «Указать другую»: редактируемое поле и
 *     «Получить код».
 *
 * Только разметка и локальная проверка формата. Запрос делает владелец шага:
 *   onSubmit(null)   — продолжить с адресом, привязанным к ticket;
 *   onSubmit(email)  — пользователь указал адрес сам.
 * Исправимые ошибки (домен, занятый адрес, формат) владелец возвращает в
 * `error` — они показываются здесь же, шаг не закрывается.
 *
 * Raw email провайдера сюда не приходит вовсе: только маска.
 */
export default function SocialEmailStep({
  maskedEmail = null,
  emailAllowed = false,
  error = '',
  loading = false,
  onSubmit,
  onRestart,
}) {
  const canUseShown = Boolean(maskedEmail) && emailAllowed;
  const [manual, setManual] = useState(!canUseShown);
  const [value, setValue] = useState('');
  const [invalid, setInvalid] = useState(false);

  const handleManualSubmit = (e) => {
    e.preventDefault();
    const email = value.trim();
    if (!isEmail(email)) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    onSubmit(email);
  };

  const restart = (
    <div className={styles.otpAux}>
      <button
        type="button"
        className={`${styles.ghost} ${styles.ghostMuted}`}
        onClick={onRestart}
      >
        Начать заново
      </button>
    </div>
  );

  // ── адрес, привязанный к регистрации: только чтение ───────────────────────
  if (!manual) {
    return (
      <div className={`${styles.authPanel} ${styles.active}`}>
        <h2 className={styles.stepTitle}>Почта для регистрации</h2>
        <p className={styles.stepDesc}>
          Код подтверждения будет отправлен на этот адрес.
        </p>

        <div className={`${styles.authField} ${styles.plainLabel}`}>
          <label htmlFor="se-shown">Электронная почта</label>
          <input type="text" id="se-shown" value={maskedEmail} readOnly />
        </div>

        {error && <div className={styles.apiError} role="alert">{error}</div>}

        <button
          type="button"
          className={styles.authBtn}
          onClick={() => onSubmit(null)}
          disabled={loading}
        >
          {loading ? 'Отправляем код…' : 'Продолжить'}
        </button>

        <div className={styles.otpAux}>
          <button
            type="button"
            className={styles.ghost}
            onClick={() => setManual(true)}
            disabled={loading}
          >
            Нет доступа к этой почте? Указать другую
          </button>
        </div>

        {restart}
      </div>
    );
  }

  // ── ввод адреса ──────────────────────────────────────────────────────────
  return (
    <form
      className={`${styles.authPanel} ${styles.active}`}
      onSubmit={handleManualSubmit}
      noValidate
    >
      <h2 className={styles.stepTitle}>Почта для регистрации</h2>
      <p className={styles.stepDesc}>
        {maskedEmail && !emailAllowed
          ? 'Для регистрации укажите почту разрешённого домена.'
          : 'Укажите электронную почту. Мы отправим на неё код подтверждения.'}
      </p>

      <div
        className={`${styles.authField} ${styles.plainLabel} ${invalid ? styles.hasErr : ''}`}
      >
        <label htmlFor="se-email">Электронная почта</label>
        <input
          type="email"
          id="se-email"
          placeholder="example@donnu.ru"
          autoComplete="email"
          value={value}
          onChange={(e) => { setValue(e.target.value); if (invalid) setInvalid(false); }}
          className={invalid ? styles.err : ''}
          aria-invalid={invalid ? 'true' : undefined}
          aria-describedby={invalid ? 'se-email-hint' : undefined}
        />
        <span className={styles.authHint} id="se-email-hint" role="alert">
          Введите корректный адрес электронной почты
        </span>
      </div>

      {error && <div className={styles.apiError} role="alert">{error}</div>}

      <button type="submit" className={styles.authBtn} disabled={loading}>
        {loading ? 'Отправляем код…' : 'Получить код'}
      </button>

      {canUseShown && (
        <div className={styles.otpAux}>
          <button
            type="button"
            className={styles.ghost}
            onClick={() => { setManual(false); setInvalid(false); }}
            disabled={loading}
          >
            Использовать {maskedEmail}
          </button>
        </div>
      )}

      {restart}
    </form>
  );
}
