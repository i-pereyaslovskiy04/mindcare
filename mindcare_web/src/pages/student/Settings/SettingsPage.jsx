import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Icon from '../../../components/Icon/Icon';
import Select from '../../../components/UI/Select/Select';
import Button from '../../../components/UI/Button/Button';
import Toggle from '../../../components/UI/Toggle/Toggle';
import { useAuth } from '../../../features/auth/AuthContext';
import { formatPhoneInput, PHONE_PLACEHOLDER } from '../../../features/admin/users/phone';
import * as authApi from '../../../api/auth.api';
import styles from './SettingsPage.module.css';

const SOCIAL_TYPES = ['Telegram', 'Instagram', 'LinkedIn', 'VK', 'Facebook', 'X (Twitter)', 'Сайт'];
const SOCIAL_TYPE_OPTIONS = SOCIAL_TYPES.map(t => ({ value: t, label: t }));

const TIMEZONE_OPTIONS = [
  { value: 'msk', label: 'Москва (UTC+3)' },
  { value: 'ekb', label: 'Екатеринбург (UTC+5)' },
];

const ROLE_LABEL = {
  student: 'Студент',
  psychologist: 'Психолог',
  supervisor: 'Супервизор',
  admin: 'Администратор',
};

function avatarLetter(name) {
  const t = (name || '').trim();
  return t ? t[0].toUpperCase() : '?';
}

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

export default function SettingsPage() {
  const { logout, refreshUser } = useAuth();
  const navigate = useNavigate();

  // ── Профиль (реальные данные текущего пользователя) ──
  const [profile, setProfile] = useState({ full_name: '', email: '', phone: '', role: '' });
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileLoadError, setProfileLoadError] = useState('');
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileError, setProfileError] = useState('');
  const [profileSuccess, setProfileSuccess] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setProfileLoading(true);
      setProfileLoadError('');
      try {
        const data = await authApi.getProfile();
        if (cancelled) return;
        setProfile({
          full_name: data.full_name || '',
          email: data.email || '',
          phone: data.phone || '',
          role: data.role || '',
        });
      } catch (err) {
        if (!cancelled) setProfileLoadError(err.message || 'Не удалось загрузить профиль');
      } finally {
        if (!cancelled) setProfileLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  async function handleSaveProfile(e) {
    e.preventDefault();
    setProfileError('');
    setProfileSuccess(false);
    setProfileSaving(true);
    // ПДн (ФИО/телефон) не логируются.
    try {
      const updated = await authApi.updateProfile({
        full_name: profile.full_name,
        phone: profile.phone || null,
      });
      setProfile((p) => ({
        ...p,
        full_name: updated.full_name || '',
        phone: updated.phone || '',
      }));
      setProfileSuccess(true);
      await refreshUser();
    } catch (err) {
      setProfileError(err.message || 'Не удалось сохранить профиль');
    } finally {
      setProfileSaving(false);
    }
  }

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

  const [notif, setNotif] = useState({
    session:  true,
    tasks:    true,
    articles: false,
    weekly:   true,
  });

  const [timezone, setTimezone] = useState('msk');

  // UI-only (нет backend API): локальные ссылки на соцсети.
  const [socials, setSocials] = useState([]);

  function toggleNotif(key) {
    setNotif((n) => ({ ...n, [key]: !n[key] }));
  }

  function updateSocial(id, field, val) {
    setSocials((s) => s.map((x) => (x.id === id ? { ...x, [field]: val } : x)));
  }

  function removeSocial(id) {
    setSocials((s) => s.filter((x) => x.id !== id));
  }

  function addSocial() {
    setSocials((s) => [...s, { id: Date.now(), type: 'Telegram', url: '' }]);
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>
        Настройки <em>аккаунта</em>
      </h1>
      <p className={styles.pageSub}>
        Личные данные, уведомления, конфиденциальность и помощь в трудный момент.
      </p>

      <div className={styles.grid}>
        {/* ---- LEFT COLUMN ---- */}
        <div className={styles.leftCol}>

          {/* Profile */}
          <div className={styles.card}>
            <h2 className={styles.sectionTitle}>Профиль</h2>

            {profileLoading ? (
              <div className={styles.empty}>Загрузка профиля…</div>
            ) : profileLoadError ? (
              <div className={styles.formError}>{profileLoadError}</div>
            ) : (
              <form onSubmit={handleSaveProfile}>
                <div className={styles.profileHead}>
                  <div className={styles.avatar}>{avatarLetter(profile.full_name)}</div>
                  <div>
                    <div className={styles.profileName}>
                      {profile.full_name || 'Без имени'}
                    </div>
                    <div className={styles.profileRole}>
                      {ROLE_LABEL[profile.role] || profile.role}
                    </div>
                  </div>
                </div>

                <div className={styles.field}>
                  <label>ФИО</label>
                  <input
                    className={styles.input}
                    value={profile.full_name}
                    onChange={(e) => {
                      const v = e.target.value;
                      setProfile((p) => ({ ...p, full_name: v }));
                      setProfileSuccess(false);
                    }}
                    placeholder="Иванов Иван Иванович"
                    disabled={profileSaving}
                    maxLength={255}
                  />
                </div>
                <div className={styles.field}>
                  <label>Email</label>
                  <input
                    className={styles.input}
                    type="email"
                    value={profile.email}
                    readOnly
                  />
                </div>
                <div className={styles.field}>
                  <label>Номер телефона</label>
                  <input
                    className={styles.input}
                    type="tel"
                    value={profile.phone}
                    onChange={(e) => {
                      const v = formatPhoneInput(e.target.value);
                      setProfile((p) => ({ ...p, phone: v }));
                      setProfileSuccess(false);
                    }}
                    placeholder={PHONE_PLACEHOLDER}
                    disabled={profileSaving}
                  />
                </div>
                <div className={styles.field}>
                  <label>Часовой пояс</label>
                  <Select
                    value={timezone}
                    options={TIMEZONE_OPTIONS}
                    onChange={setTimezone}
                  />
                </div>

                {profileError && <div className={styles.formError}>{profileError}</div>}
                {profileSuccess && <div className={styles.formSuccess}>Изменения сохранены.</div>}

                <Button
                  type="submit"
                  variant="primary"
                  style={{ marginTop: 6 }}
                  loading={profileSaving}
                >
                  Сохранить изменения
                </Button>
              </form>
            )}
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

        {/* ---- RIGHT COLUMN ---- */}
        <div className={styles.rightCol}>

          {/* Social networks */}
          <div className={styles.card}>
            <div className={styles.socialHead}>
              <h2 className={styles.sectionTitle}>Социальные сети</h2>
              <span className={styles.socialCount}>
                {socials.length} {socials.length === 1 ? 'ссылка' : socials.length < 5 ? 'ссылки' : 'ссылок'}
              </span>
            </div>
            <p className={styles.socialDesc}>
              Добавьте ссылки на свои профили — это видит только ваш психолог.
            </p>

            {socials.length === 0 && (
              <div className={styles.empty}>Пока ничего не добавлено</div>
            )}

            {socials.map((s) => (
              <div key={s.id} className={styles.socialRow}>
                <Select
                  value={s.type}
                  options={SOCIAL_TYPE_OPTIONS}
                  onChange={(val) => updateSocial(s.id, 'type', val)}
                />
                <input
                  className={`${styles.input} ${styles.socialUrl}`}
                  placeholder="@username или ссылка"
                  value={s.url}
                  onChange={(e) => updateSocial(s.id, 'url', e.target.value)}
                />
                <button
                  className={styles.socialDel}
                  onClick={() => removeSocial(s.id)}
                  title="Удалить"
                  type="button"
                ><Icon name="trash" size={14} /></button>
              </div>
            ))}

            <Button variant="ghost" style={{ marginTop: 6 }} onClick={addSocial}>
              <Icon name="plus" size={14} /> Добавить ссылку
            </Button>
          </div>

          {/* Notifications */}
          <div className={styles.card}>
            <h2 className={styles.sectionTitle} style={{ marginBottom: 14 }}>Уведомления</h2>
            <NotifRow
              label="Напоминания о сессиях"
              desc="За день и за час до встречи"
              on={notif.session}
              onToggle={() => toggleNotif('session')}
            />
            <NotifRow
              label="Задания психолога"
              desc="Когда специалист добавляет новое"
              on={notif.tasks}
              onToggle={() => toggleNotif('tasks')}
            />
            <NotifRow
              label="Новые материалы"
              desc="Подборка по вашим темам — раз в неделю"
              on={notif.articles}
              onToggle={() => toggleNotif('articles')}
            />
            <NotifRow
              label="Еженедельный итог"
              desc="Динамика настроения и прогресс по целям"
              on={notif.weekly}
              onToggle={() => toggleNotif('weekly')}
            />
          </div>

          {/* Crisis help */}
          <div className={`${styles.card} ${styles.cardCrisis}`}>
            <div className={styles.crisisInner}>
              <div className={styles.crisisIcon}>
                <Icon name="bell" size={18} />
              </div>
              <div>
                <h3 className={styles.crisisTitle}>Помощь в кризисный момент</h3>
                <p className={styles.crisisText}>
                  Если совсем плохо и нужна поддержка прямо сейчас — это нормально просить о ней.
                </p>
                <div className={styles.crisisBtns}>
                  <a
                    href="tel:88002000122"
                    className={`${styles.btn} ${styles.btnSoft} ${styles.btnCrisis}`}
                  >
                    Телефон доверия 8-800-2000-122
                  </a>
                  <Button variant="ghost">
                    Связаться с дежурным
                  </Button>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
