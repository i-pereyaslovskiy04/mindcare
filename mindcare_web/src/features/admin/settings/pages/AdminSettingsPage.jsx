import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../../../../components/UI/Button/Button';
import { useAuth } from '../../../auth/AuthContext';
import * as authApi from '../../../../api/auth.api';
import styles from './AdminSettingsPage.module.css';

export default function AdminSettingsPage() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const [pwForm, setPwForm] = useState({
    current_password: '',
    new_password: '',
    new_password_confirm: '',
  });
  const [pwLoading, setPwLoading] = useState(false);
  const [pwError, setPwError] = useState('');
  const [pwSuccess, setPwSuccess] = useState(false);

  async function handleChangePassword(e) {
    e.preventDefault();
    setPwError('');
    setPwSuccess(false);

    if (!pwForm.current_password || !pwForm.new_password || !pwForm.new_password_confirm) {
      setPwError('Заполните все поля.');
      return;
    }

    setPwLoading(true);
    try {
      await authApi.changePassword(pwForm);
      setPwSuccess(true);
      setTimeout(async () => {
        navigate('/', { replace: true, state: { openAuth: 'login', message: 'Пароль изменён. Войдите снова.' } });
        await logout();
      }, 1500);
    } catch (err) {
      setPwError(err.message || 'Не удалось сменить пароль. Попробуйте позже.');
    } finally {
      setPwLoading(false);
    }
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>Настройки</h1>

      <div className={styles.card}>
        <h2 className={styles.cardTitle}>Безопасность</h2>
        <p className={styles.cardDesc}>
          Изменение пароля администратора. После успешной смены потребуется войти снова.
        </p>

        <form onSubmit={handleChangePassword}>
          <div className={styles.field}>
            <label htmlFor="adm-cur-pw">Текущий пароль</label>
            <input
              id="adm-cur-pw"
              className={styles.input}
              type="password"
              value={pwForm.current_password}
              onChange={(e) => setPwForm(f => ({ ...f, current_password: e.target.value }))}
              disabled={pwLoading || pwSuccess}
              autoComplete="current-password"
            />
          </div>
          <div className={styles.field}>
            <label htmlFor="adm-new-pw">Новый пароль</label>
            <input
              id="adm-new-pw"
              className={styles.input}
              type="password"
              value={pwForm.new_password}
              onChange={(e) => setPwForm(f => ({ ...f, new_password: e.target.value }))}
              disabled={pwLoading || pwSuccess}
              autoComplete="new-password"
            />
          </div>
          <div className={styles.field}>
            <label htmlFor="adm-confirm-pw">Повторите новый пароль</label>
            <input
              id="adm-confirm-pw"
              className={styles.input}
              type="password"
              value={pwForm.new_password_confirm}
              onChange={(e) => setPwForm(f => ({ ...f, new_password_confirm: e.target.value }))}
              disabled={pwLoading || pwSuccess}
              autoComplete="new-password"
            />
          </div>

          {pwError && <div className={styles.formError} role="alert">{pwError}</div>}
          {pwSuccess && <div className={styles.formSuccess} role="status">Пароль изменён. Войдите снова.</div>}

          <Button
            type="submit"
            variant="primary"
            loading={pwLoading}
            disabled={pwSuccess}
          >
            Сменить пароль
          </Button>
        </form>
      </div>
    </div>
  );
}
