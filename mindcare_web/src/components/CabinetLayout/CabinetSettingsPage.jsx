import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';
import Button from '../UI/Button/Button';
import Toggle from '../UI/Toggle/Toggle';
import { getInitials } from '../../shared/lib/utils';
import { ROLE_LABELS } from '../../shared/lib/roles';
import Select from '../UI/Select/Select';
import * as authApi from '../../api/auth.api';
import styles from './CabinetSettingsPage.module.css';

const TIMEZONE_OPTIONS = [
  { value: 'msk', label: 'Москва (UTC+3)' },
  { value: 'ekb', label: 'Екатеринбург (UTC+5)' },
  { value: 'nsk', label: 'Новосибирск (UTC+7)' },
];

function NotifRow({ label, desc, on, onToggle }) {
  return (
    <div className={styles.notifRow}>
      <div>
        <div className={styles.notifLabel}>{label}</div>
        <div className={styles.notifDesc}>{desc}</div>
      </div>
      <Toggle checked={on} onChange={onToggle} label={label} />
    </div>
  );
}

export default function CabinetSettingsPage({ cabinetRole }) {
  const { user, logout } = useAuth();
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
    setPwLoading(true);
    try {
      await authApi.changePassword(pwForm);
      setPwSuccess(true);
      setTimeout(async () => {
        navigate('/', { replace: true, state: { openAuth: 'login', message: 'Пароль изменён. Войдите снова.' } });
        await logout();
      }, 1500);
    } catch (err) {
      setPwError(err.message || 'Ошибка смены пароля');
    } finally {
      setPwLoading(false);
    }
  }

  const [timezone, setTimezone] = useState('msk');

  const [notif, setNotif] = useState({
    sessions: true,
    messages: true,
    weekly:   false,
  });

  // Лейбл — из роли МАРШРУТА (cabinetRole), а не legacy user.role.
  const roleLabel = ROLE_LABELS[cabinetRole] ?? '';

  function toggleNotif(key) {
    setNotif(n => ({ ...n, [key]: !n[key] }));
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>
        Настройки <em>аккаунта</em>
      </h1>
      <p className={styles.pageSub}>
        Личные данные, уведомления и конфиденциальность.
      </p>

      <div className={styles.grid}>
        {/* LEFT — Profile */}
        <div className={styles.leftCol}>
          <div className={styles.card}>
            <h2 className={styles.sectionTitle}>Профиль</h2>

            <div className={styles.profileHead}>
              <div className={styles.avatar}>{getInitials(user?.name)}</div>
              <div>
                <div className={styles.profileName}>{user?.name ?? '—'}</div>
                <div className={styles.profileRole}>{roleLabel}</div>
                <Button
                  variant="ghost"
                  size="sm"
                  style={{ marginTop: 8 }}
                >
                  Изменить фото
                </Button>
              </div>
            </div>

            <div className={styles.field}>
              <label>Имя</label>
              <input className={styles.input} defaultValue={user?.name ?? ''} />
            </div>
            <div className={styles.field}>
              <label>Email</label>
              <input className={styles.input} type="email" defaultValue={user?.email ?? ''} readOnly />
            </div>
            <div className={styles.field}>
              <label>Номер телефона</label>
              <input className={styles.input} type="tel" placeholder="+7 (___) ___-__-__" />
            </div>
            <div className={styles.field}>
              <label>Часовой пояс</label>
              <Select
                value={timezone}
                options={TIMEZONE_OPTIONS}
                onChange={setTimezone}
              />
            </div>

            <Button variant="primary" style={{ marginTop: 6 }}>
              Сохранить изменения
            </Button>
          </div>

          {/* Security */}
          <div className={styles.card}>
            <h2 className={styles.sectionTitle}>Безопасность</h2>
            <form onSubmit={handleChangePassword}>
              <div className={styles.field}>
                <label>Текущий пароль</label>
                <input
                  className={styles.input}
                  type="password"
                  value={pwForm.current_password}
                  onChange={(e) => setPwForm(f => ({ ...f, current_password: e.target.value }))}
                  required
                  disabled={pwLoading || pwSuccess}
                  autoComplete="current-password"
                />
              </div>
              <div className={styles.field}>
                <label>Новый пароль</label>
                <input
                  className={styles.input}
                  type="password"
                  value={pwForm.new_password}
                  onChange={(e) => setPwForm(f => ({ ...f, new_password: e.target.value }))}
                  required
                  disabled={pwLoading || pwSuccess}
                  autoComplete="new-password"
                />
              </div>
              <div className={styles.field}>
                <label>Подтверждение нового пароля</label>
                <input
                  className={styles.input}
                  type="password"
                  value={pwForm.new_password_confirm}
                  onChange={(e) => setPwForm(f => ({ ...f, new_password_confirm: e.target.value }))}
                  required
                  disabled={pwLoading || pwSuccess}
                  autoComplete="new-password"
                />
              </div>
              {pwError && <div className={styles.formError}>{pwError}</div>}
              {pwSuccess && <div className={styles.formSuccess}>Пароль изменён. Войдите снова.</div>}
              <Button
                type="submit"
                variant="primary"
                style={{ marginTop: 6 }}
                loading={pwLoading}
                disabled={pwSuccess}
              >
                Изменить пароль
              </Button>
            </form>
          </div>
        </div>

        {/* RIGHT — Notifications */}
        <div className={styles.rightCol}>
          <div className={styles.card}>
            <h2 className={styles.sectionTitle} style={{ marginBottom: 14 }}>Уведомления</h2>
            <NotifRow
              label="Напоминания о сессиях"
              desc="За день и за час до встречи"
              on={notif.sessions}
              onToggle={() => toggleNotif('sessions')}
            />
            <NotifRow
              label="Новые сообщения"
              desc="Когда приходит новое сообщение"
              on={notif.messages}
              onToggle={() => toggleNotif('messages')}
            />
            <NotifRow
              label="Еженедельный итог"
              desc="Сводка за неделю по понедельникам"
              on={notif.weekly}
              onToggle={() => toggleNotif('weekly')}
            />
          </div>

        </div>
      </div>
    </div>
  );
}
