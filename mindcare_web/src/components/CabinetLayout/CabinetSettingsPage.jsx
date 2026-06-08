import { useState } from 'react';
import { useAuth, useLogout } from '../../features/auth/AuthContext';
import Icon from '../../pages/student/components/Icon';
import styles from './CabinetSettingsPage.module.css';

const ROLE_LABELS = {
  psychologist: 'Психолог',
  supervisor:   'Супервизор',
};

function getInitials(name) {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  return parts.length >= 2
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : parts[0].slice(0, 2).toUpperCase();
}

function Toggle({ on, onToggle }) {
  return (
    <button
      type="button"
      className={`${styles.toggle} ${on ? styles.toggleOn : ''}`}
      onClick={onToggle}
      aria-pressed={on}
    />
  );
}

function NotifRow({ label, desc, on, onToggle }) {
  return (
    <div className={styles.notifRow}>
      <div>
        <div className={styles.notifLabel}>{label}</div>
        <div className={styles.notifDesc}>{desc}</div>
      </div>
      <Toggle on={on} onToggle={onToggle} />
    </div>
  );
}

export default function CabinetSettingsPage() {
  const { user } = useAuth();
  const logout   = useLogout();

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
                <button
                  type="button"
                  className={`${styles.btn} ${styles.btnGhost}`}
                  style={{ padding: '4px 10px', fontSize: 11.5, marginTop: 8 }}
                >
                  Изменить фото
                </button>
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
              <select className={styles.select} defaultValue="msk">
                <option value="msk">Москва (UTC+3)</option>
                <option value="ekb">Екатеринбург (UTC+5)</option>
                <option value="nsk">Новосибирск (UTC+7)</option>
              </select>
            </div>

            <button type="button" className={`${styles.btn} ${styles.btnPrimary}`} style={{ marginTop: 6 }}>
              Сохранить изменения
            </button>
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
            <button type="button" className={`${styles.btn} ${styles.btnGhost}`} onClick={logout}>
              <Icon name="logout" size={14} /> Выйти
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
