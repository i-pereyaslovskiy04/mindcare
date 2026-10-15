import { useEffect, useRef, useState } from 'react';
import Button from '../../../components/UI/Button/Button';
import Modal from '../../../components/Modal/Modal';
import TextField from '../../../components/UI/TextField/TextField';
import * as authApi from '../../../api/auth.api';
import ForgotPasswordModal from '../../auth/forgot-password/ForgotPasswordModal';
import styles from './AccountSettings.module.css';

const PASSWORD_CHANGED_MESSAGE = 'Пароль изменён. Войдите снова.';
const PASSWORD_SET_MESSAGE = 'Пароль установлен. Войдите снова.';
const END_SESSION_DELAY_MS = 1500;

function ChangePasswordCard({ endSession }) {
  const [form, setForm] = useState({
    current_password: '', new_password: '', new_password_confirm: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setSuccess(false);
    setLoading(true);
    try {
      await authApi.changePassword(form);
      setSuccess(true);
      // Сессии на сервере отозваны: уходим на публичную страницу, затем
      // очищаем клиентскую авторизацию (без logout — он вернул бы 401).
      timer.current = setTimeout(() => endSession(PASSWORD_CHANGED_MESSAGE), END_SESSION_DELAY_MS);
    } catch (err) {
      setError(err.message || 'Ошибка смены пароля');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className={styles.card} aria-labelledby="settings-password-title">
      <h2 id="settings-password-title" className={styles.sectionTitle}>Смена пароля</h2>
      <form className={styles.form} onSubmit={handleSubmit}>
        <TextField
          id="settings-current-password"
          label="Текущий пароль"
          type="password"
          value={form.current_password}
          onChange={set('current_password')}
          required
          disabled={loading || success}
          autoComplete="current-password"
        />
        <TextField
          id="settings-new-password"
          label="Новый пароль"
          type="password"
          value={form.new_password}
          onChange={set('new_password')}
          required
          disabled={loading || success}
          autoComplete="new-password"
        />
        <TextField
          id="settings-new-password-confirm"
          label="Подтверждение нового пароля"
          type="password"
          value={form.new_password_confirm}
          onChange={set('new_password_confirm')}
          required
          disabled={loading || success}
          autoComplete="new-password"
        />
        {error && <div className={styles.formError} role="alert">{error}</div>}
        {success && <div className={styles.formSuccess} role="status">{PASSWORD_CHANGED_MESSAGE}</div>}
        <div className={styles.actions}>
          <Button type="submit" variant="primary" loading={loading} disabled={success}>
            Изменить пароль
          </Button>
        </div>
      </form>
    </section>
  );
}

function SetPasswordCard({ email, endSession }) {
  const [open, setOpen] = useState(false);
  return (
    <section className={styles.card} aria-labelledby="settings-set-password-title">
      <h2 id="settings-set-password-title" className={styles.sectionTitle}>Пароль не задан</h2>
      <p className={styles.dangerText}>
        Вы входите через внешний сервис, поэтому пароля у аккаунта пока нет. Чтобы входить
        по email и паролю, установите пароль: мы отправим код подтверждения на {email || 'почту аккаунта'}.
        После установки пароля нужно будет войти заново.
      </p>
      <Button type="button" variant="primary" onClick={() => setOpen(true)} disabled={!email}>
        Установить пароль по email
      </Button>
      <ForgotPasswordModal
        open={open}
        onClose={() => setOpen(false)}
        initialEmail={email}
        emailLocked
        onCompleted={() => endSession(PASSWORD_SET_MESSAGE)}
      />
    </section>
  );
}

function DeactivationCard({ deactivateOwnAccount, endSession }) {
  const [open, setOpen] = useState(false);
  const [deactivating, setDeactivating] = useState(false);
  const [error, setError] = useState('');

  async function handleConfirm() {
    setError('');
    setDeactivating(true);
    try {
      await deactivateOwnAccount();
    } catch (err) {
      setError(err.message || 'Не удалось отключить аккаунт');
      setDeactivating(false);
      return;
    }
    // Сессии уже отозваны на сервере: сначала публичная страница, затем очистка (как useLogout).
    endSession('Аккаунт отключён. Для восстановления обратитесь к администратору.');
  }

  return (
    <>
      <section className={`${styles.card} ${styles.cardDanger}`} aria-labelledby="settings-deactivate-title">
        <h2 id="settings-deactivate-title" className={styles.sectionTitle}>Отключение аккаунта</h2>
        <p className={styles.dangerText}>
          Вы потеряете доступ к MindCare на всех устройствах. Ваши данные
          и email сохранятся — восстановить аккаунт может только
          администратор по вашему обращению.
        </p>
        <Button type="button" variant="danger" onClick={() => { setError(''); setOpen(true); }}>
          Отключить аккаунт
        </Button>
      </section>

      <Modal
        open={open}
        onClose={() => { if (!deactivating) setOpen(false); }}
        ariaLabel="Подтверждение отключения аккаунта"
      >
        <div className={styles.confirmBody}>
          <h2 className={styles.sectionTitle}>Отключить аккаунт?</h2>
          <ul className={styles.confirmList}>
            <li>Доступ к аккаунту прекратится, все сессии будут завершены.</li>
            <li>Ваши данные и email сохранятся.</li>
            <li>Восстановить аккаунт можно только через администратора.</li>
          </ul>
          {error && <div className={styles.formError} role="alert">{error}</div>}
          <div className={styles.confirmActions}>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setOpen(false)}
              disabled={deactivating}
            >
              Отмена
            </Button>
            <Button type="button" variant="danger" onClick={handleConfirm} loading={deactivating}>
              Отключить аккаунт
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

/**
 * Раздел «Безопасность»: смена пароля (если он есть) либо установка пароля по
 * email-коду; отключение аккаунта (только чистый студент вне impersonation).
 * endSession(message) — navigate на публичную страницу, затем clearSession().
 */
export default function SecuritySection({
  hasPassword, email, canSelfDeactivate, deactivateOwnAccount, endSession,
}) {
  return (
    <div className={styles.stack}>
      {hasPassword
        ? <ChangePasswordCard endSession={endSession} />
        : <SetPasswordCard email={email} endSession={endSession} />}
      {canSelfDeactivate && (
        <DeactivationCard deactivateOwnAccount={deactivateOwnAccount} endSession={endSession} />
      )}
    </div>
  );
}
