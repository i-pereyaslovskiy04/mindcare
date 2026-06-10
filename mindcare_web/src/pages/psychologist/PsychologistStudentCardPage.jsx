import { useParams, Link } from 'react-router-dom';
import Icon from '../../components/Icon/Icon';
import Badge from '../../components/UI/Badge/Badge';
import Button from '../../components/UI/Button/Button';
import { getInitials } from '../../shared/lib/utils';
import { useStudentCard } from '../../features/psychologist/hooks/useStudentCard';
import styles from './PsychologistStudentCardPage.module.css';

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

function getDuration(iso) {
  if (!iso) return null;
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days < 1)  return 'Сегодня';
  if (days === 1) return '1 день';
  if (days < 5)  return `${days} дня`;
  return `${days} дней`;
}

const ACTIONS = [
  { icon: 'chat',     label: 'Чат',              title: 'Чат будет доступен в следующих версиях' },
  { icon: 'calendar', label: 'Расписание',        title: 'Расписание будет доступно позже' },
  { icon: 'diary',    label: 'Заметки',           title: 'Рабочие заметки будут добавлены позже' },
  { icon: 'articles', label: 'Материалы и тесты', title: 'Назначение материалов появится позже' },
];

const FUTURE_ITEMS = [
  'История консультаций и сессий',
  'Рабочие заметки психолога',
  'Назначенные материалы и тесты',
  'Результаты психодиагностики',
  'Запрос супервизии',
];

export default function PsychologistStudentCardPage() {
  const { studentId } = useParams();
  const numericId = parseInt(studentId, 10);
  const isValidId = !isNaN(numericId) && numericId > 0;
  const { student, loading, error, refetch } = useStudentCard(isValidId ? numericId : null);

  const is404 = Boolean(
    error && (
      error.includes('404') ||
      error.toLowerCase().includes('не найден') ||
      error.toLowerCase().includes('not found')
    )
  );

  return (
    <div className={styles.page}>
      <Link to="/psychologist/students" className={styles.backLink}>
        <Icon name="chevron-left" size={16} />
        Назад к студентам
      </Link>

      <div className={styles.header}>
        <div className={styles.labelTag}>Кабинет психолога</div>
        <h1 className={styles.pageTitle}>Карточка <em>студента</em></h1>
        <p className={styles.pageSub}>Базовая информация о студенте и сопровождении.</p>
      </div>

      {/* Invalid ID state */}
      {!isValidId && (
        <div className={styles.stateBox}>
          <div className={styles.stateIconWrap}>
            <Icon name="bell" size={28} />
          </div>
          <div className={styles.stateTitle}>Некорректный адрес карточки</div>
          <div className={styles.stateText}>
            Проверьте ссылку или вернитесь к списку студентов.
          </div>
        </div>
      )}

      {/* Loading skeleton */}
      {isValidId && loading && (
        <>
          <div className={styles.skeletonHero}>
            <div className={styles.skeletonAvatar} />
            <div className={styles.skeletonHeroInfo}>
              <div className={`${styles.skeletonLine} ${styles.wide}`} />
              <div className={`${styles.skeletonLine} ${styles.medium}`} />
              <div className={`${styles.skeletonLine} ${styles.short}`} />
            </div>
          </div>
          <div className={styles.skeletonInfoGrid}>
            {[1, 2, 3, 4].map(i => <div key={i} className={styles.skeletonInfoCard} />)}
          </div>
        </>
      )}

      {/* Error state */}
      {isValidId && !loading && error && (
        <div className={styles.stateBox}>
          <div className={styles.stateIconWrap}>
            <Icon name="bell" size={28} />
          </div>
          <div className={styles.stateTitle}>
            {is404 ? 'Карточка недоступна' : 'Не удалось загрузить данные'}
          </div>
          <div className={styles.stateText}>
            {is404
              ? 'Студент не найден или не назначен вам.'
              : error}
          </div>
          {!is404 && (
            <Button variant="secondary" onClick={refetch}>Повторить</Button>
          )}
        </div>
      )}

      {/* Content */}
      {isValidId && !loading && !error && student && (
        <>
          {/* Hero card */}
          <div className={styles.heroCard}>
            <div className={styles.heroAvatar}>
              {getInitials(student.full_name)}
            </div>
            <div className={styles.heroInfo}>
              <div className={styles.heroBadge}>Активное сопровождение</div>
              <h2 className={styles.heroName}>{student.full_name}</h2>
              <div className={styles.heroEmail}>
                <Icon name="mail" size={14} />
                <span>{student.email}</span>
              </div>
              <div className={styles.heroMeta}>
                <span>Назначен {formatDate(student.assigned_at)}</span>
                {getDuration(student.assigned_at) && (
                  <span className={styles.heroDuration}>
                    {getDuration(student.assigned_at)}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Info cards */}
          <div className={styles.infoGrid}>
            <div className={styles.infoCard}>
              <div className={styles.infoLabel}>Статус</div>
              <div className={styles.infoValue}>
                <Badge tone="success">Активен</Badge>
              </div>
            </div>
            <div className={styles.infoCard}>
              <div className={styles.infoLabel}>Назначен</div>
              <div className={styles.infoValue}>{formatDate(student.assigned_at)}</div>
            </div>
            <div className={styles.infoCard}>
              <div className={styles.infoLabel}>Сопровождение</div>
              <div className={styles.infoValue}>{getDuration(student.assigned_at) ?? '—'}</div>
            </div>
            <div className={styles.infoCard}>
              <div className={styles.infoLabel}>Контакт</div>
              <div className={`${styles.infoValue} ${styles.emailVal}`}>{student.email}</div>
            </div>
          </div>

          {/* Quick actions */}
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Быстрые действия</h3>
            <div className={styles.actionsGrid}>
              {ACTIONS.map(({ icon, label, title }) => (
                <button key={label} className={styles.actionCard} disabled title={title}>
                  <div className={styles.actionIcon}>
                    <Icon name={icon} size={22} />
                  </div>
                  <div className={styles.actionLabel}>{label}</div>
                  <span className={styles.soonTag}>скоро</span>
                </button>
              ))}
            </div>
          </div>

          {/* Future block */}
          <div className={styles.futureBlock}>
            <div className={styles.futureTitle}>Что появится в карточке позже</div>
            <ul className={styles.futureList}>
              {FUTURE_ITEMS.map(text => (
                <li key={text} className={styles.futureItem}>
                  <span className={styles.futureDot} />
                  {text}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
