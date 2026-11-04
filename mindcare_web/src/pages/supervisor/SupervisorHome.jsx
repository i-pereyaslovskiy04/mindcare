import { Link } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';
import usePendingVerificationsCount from '../../features/studentVerification/hooks/usePendingVerificationsCount';
import useReviewQueueCounts from '../../features/moderation/hooks/useReviewQueueCounts';
import Icon from '../../components/Icon/Icon';
import { NEUTRAL_GREETING } from '../../shared/lib/greeting';
import { normalizeRoles } from '../../shared/lib/roles';
import styles from '../../components/CabinetLayout/CabinetHome.module.css';

// Быстрые ссылки — только на работающие разделы меню супервизора.
const QUICK_LINKS = [
  { to: '/supervisor/engagements', icon: 'tasks', title: 'Назначение психологов', desc: 'Сопровождение студентов' },
  { to: '/supervisor/materials', icon: 'articles', title: 'Материалы', desc: 'Проверка и свои статьи' },
  { to: '/supervisor/tests', icon: 'tests', title: 'Тесты', desc: 'Проверка методик' },
  { to: '/supervisor/campaigns', icon: 'tests', title: 'Тестирование по ссылке', desc: 'Кампании и выгрузка xlsx' },
  { to: '/supervisor/student-verifications', icon: 'check', title: 'Подтверждение студентов', desc: 'Заявки ДонГУ' },
];

function StatCard({ label, value, desc }) {
  return (
    <div className={styles.statCard} role="group" aria-label={label}>
      <div className={styles.statLabel}>{label}</div>
      <div className={styles.statValue}>{value ?? '—'}</div>
      <div className={styles.statDesc}>{desc}</div>
    </div>
  );
}

export default function SupervisorHome() {
  const { user, isImpersonating } = useAuth();
  const today    = new Date().toLocaleDateString('ru-RU', {
    weekday: 'long', day: 'numeric', month: 'long',
  });
  // Те же условия, что у бейджей меню (SupervisorLayout): очереди видит только
  // прямой supervisor вне режима «под именем».
  const canReview = !isImpersonating && normalizeRoles(user).includes('supervisor');
  const pendingVerifications = usePendingVerificationsCount(canReview, user?.id ?? null);
  const reviewCounts = useReviewQueueCounts(canReview, user?.id ?? null);

  return (
    <div className={styles.page}>
      <div className={styles.labelTag}>{today}</div>
      <h1 className={styles.pageTitle}>{NEUTRAL_GREETING}</h1>
      <p className={styles.pageSub}>
        Кабинет супервизора: сопровождение, проверка материалов и тестов, заявки студентов.
      </p>

      <div className={`${styles.grid} ${styles.g21}`} style={{ marginBottom: 16 }}>
        <div className={styles.darkCard} data-hero-banner>
          <div className={styles.darkCardTitle}>
            Кабинет<br /><em>супервизора</em>
          </div>
          <div className={styles.darkCardSub}>
            Очереди проверки — в показателях ниже и в бейджах меню.
          </div>
          <div className={styles.darkCardBtns}>
            <Link to="/supervisor/settings" className={`${styles.btn} ${styles.btnLatte}`}>
              Настройки профиля
            </Link>
          </div>
        </div>

        <div className={styles.card} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className={styles.sectionTitle}>Разделы</div>
          {QUICK_LINKS.map((item) => (
            <Link key={item.to} to={item.to} className={`${styles.liRow} ${styles.liLink}`}>
              <div className={styles.liIcon}><Icon name={item.icon} size={18} /></div>
              <div className={styles.liBody}>
                <div className={styles.liTitle}>{item.title}</div>
                <div className={styles.liDesc}>{item.desc}</div>
              </div>
            </Link>
          ))}
        </div>
      </div>

      <div className={`${styles.grid} ${styles.g3}`} style={{ marginBottom: 16 }}>
        <StatCard label="Тесты на проверке" value={reviewCounts.tests} desc="Ожидают решения" />
        <StatCard label="Материалы на проверке" value={reviewCounts.articles} desc="Ожидают решения" />
        <StatCard label="Заявки на подтверждение" value={pendingVerifications} desc="Статус студента ДонГУ" />
      </div>
    </div>
  );
}
