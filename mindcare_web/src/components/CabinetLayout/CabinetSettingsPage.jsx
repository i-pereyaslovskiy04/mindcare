import { useState } from 'react';
import { useAuth, useLogout } from '../../features/auth/AuthContext';
import Icon from '../Icon/Icon';
import Button from '../UI/Button/Button';
import Toggle from '../UI/Toggle/Toggle';
import { getInitials } from '../../shared/lib/utils';
import Select from '../UI/Select/Select';
import styles from './CabinetSettingsPage.module.css';

const ROLE_LABELS = {
  psychologist: 'Психолог',
  supervisor:   'Супервизор',
};

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

export default function CabinetSettingsPage() {
  const { user } = useAuth();
  const logout   = useLogout();

  const [timezone, setTimezone] = useState('msk');

  const [notif, setNotif] = useState({
    sessions: true,
    messages: true,
    weekly:   false,
  });

  const roleLabel = ROLE_LABELS[user?.role] ?? '';

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
        </div>

        {/* RIGHT — Notifications + Logout */}
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

          <div className={`${styles.card} ${styles.logoutCard}`}>
            <div>
              <div className={styles.logoutLabel}>Выйти из аккаунта</div>
              <div className={styles.logoutSub}>Сессия будет завершена на этом устройстве</div>
            </div>
            <Button variant="ghost" onClick={logout}>
              <Icon name="logout" size={14} /> Выйти
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
