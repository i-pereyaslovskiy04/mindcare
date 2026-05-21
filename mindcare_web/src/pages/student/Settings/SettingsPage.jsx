import { useState } from 'react';
import Icon from '../components/Icon';
import styles from './SettingsPage.module.css';

const SOCIAL_TYPES = ['Telegram', 'Instagram', 'LinkedIn', 'VK', 'Facebook', 'X (Twitter)', 'Сайт'];

function Toggle({ on, onToggle }) {
  return (
    <button
      className={`${styles.toggle} ${on ? styles.toggleOn : ''}`}
      onClick={onToggle}
      aria-pressed={on}
      type="button"
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

export default function SettingsPage() {
  const [notif, setNotif] = useState({
    session:  true,
    tasks:    true,
    articles: false,
    weekly:   true,
  });

  const [socials, setSocials] = useState([
    { id: 1, type: 'Telegram',   url: '@anna_polina' },
    { id: 2, type: 'Instagram',  url: '' },
  ]);

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

            <div className={styles.profileHead}>
              <div className={styles.avatar}>А</div>
              <div>
                <div className={styles.profileName}>Анна Полина</div>
                <div className={styles.profileRole}>Студент · 3 курс · ФЦиЯ</div>
                <button className={`${styles.btn} ${styles.btnGhost}`} style={{ padding: '4px 10px', fontSize: 11.5, marginTop: 8 }}>
                  Изменить фото
                </button>
              </div>
            </div>

            <div className={styles.field}>
              <label>Имя</label>
              <input className={styles.input} defaultValue="Анна" />
            </div>
            <div className={styles.field}>
              <label>Фамилия</label>
              <input className={styles.input} defaultValue="Полина" />
            </div>
            <div className={styles.field}>
              <label>Email</label>
              <input className={styles.input} type="email" defaultValue="a.polina@donnu.ru" />
            </div>
            <div className={styles.field}>
              <label>Номер телефона</label>
              <input className={styles.input} type="tel" placeholder="+7 (___) ___-__-__" defaultValue="+7 (949) 312-04-78" />
            </div>
            <div className={styles.field}>
              <label>Часовой пояс</label>
              <select className={styles.select} defaultValue="msk">
                <option value="msk">Москва (UTC+3)</option>
                <option value="ekb">Екатеринбург (UTC+5)</option>
              </select>
            </div>

            <button className={`${styles.btn} ${styles.btnPrimary}`} style={{ marginTop: 6 }}>
              Сохранить изменения
            </button>
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
                <select
                  className={`${styles.select} ${styles.socialType}`}
                  value={s.type}
                  onChange={(e) => updateSocial(s.id, 'type', e.target.value)}
                >
                  {SOCIAL_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
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

            <button
              className={`${styles.btn} ${styles.btnGhost}`}
              style={{ marginTop: 6 }}
              onClick={addSocial}
            >
              <Icon name="plus" size={14} /> Добавить ссылку
            </button>
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
                  <button className={`${styles.btn} ${styles.btnGhost}`}>
                    Связаться с дежурным
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Logout */}
          <div className={`${styles.card} ${styles.logoutCard}`}>
            <div>
              <div className={styles.logoutLabel}>Выйти из аккаунта</div>
              <div className={styles.logoutSub}>Сессия будет завершена на этом устройстве</div>
            </div>
            <button className={`${styles.btn} ${styles.btnGhost}`}>
              <Icon name="logout" size={14} /> Выйти
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
