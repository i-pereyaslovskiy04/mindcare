import { useLocation } from 'react-router-dom';
import Sidebar from './components/Sidebar/Sidebar';
import Icon from './components/Icon';
import styles from './StudentLayout.module.css';

const CRUMB_LABELS = {
  '/student':           'Главная',
  '/student/diary':     'Дневник состояния',
  '/student/tests':     'Тесты',
  '/student/articles':  'Материалы и статьи',
  '/student/tasks':     'Задания психолога',
  '/student/chat':      'Чат с психологом',
  '/student/goals':     'Цели терапии',
  '/student/calendar':  'Календарь и сессии',
  '/student/settings':  'Настройки',
};

export default function StudentLayout({ children }) {
  const { pathname } = useLocation();
  const crumb = CRUMB_LABELS[pathname] ?? 'Кабинет';

  return (
    <div className={styles.app}>
      <Sidebar />

      <main className={styles.main}>
        <div className={styles.topbar}>
          <div className={styles.crumbs}>
            Личный кабинет / <span>{crumb}</span>
          </div>
          <div className={styles.actions}>
            <div className={styles.search}>
              <Icon name="search" size={14} />
              <input type="text" placeholder="Поиск по материалам, записям…" />
            </div>
            <button className={styles.iconBtn} aria-label="Уведомления">
              <Icon name="bell" size={16} />
              <span className={styles.dot} />
            </button>
          </div>
        </div>

        <div className={styles.content}>
          <div className={styles.contentInner}>
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}
