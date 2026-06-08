import { Link } from 'react-router-dom';
import Icon from '../../components/Icon/Icon';
import { getInitials } from '../../shared/lib/utils';
import { useMyStudents } from '../../features/psychologist/hooks/useMyStudents';
import styles from './PsychologistStudentsPage.module.css';

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

export default function PsychologistStudentsPage() {
  const { items, loading, error, total, page, setPage, query, setQuery, refetch } =
    useMyStudents();

  const totalPages = Math.max(1, Math.ceil(total / 20));

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.header}>
        <div>
          <div className={styles.labelTag}>Кабинет психолога</div>
          <h1 className={styles.pageTitle}>Мои <em>студенты</em></h1>
          <p className={styles.pageSub}>
            Студенты, назначенные вам супервизором для сопровождения.
          </p>
        </div>
        <div className={styles.searchWrap}>
          <Icon name="search" size={16} />
          <input
            className={styles.searchInput}
            type="text"
            placeholder="Поиск по ФИО или email…"
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Loading — skeleton cards */}
      {loading && (
        <div className={styles.skeletonGrid}>
          {[1, 2, 3, 4].map(i => (
            <div key={i} className={styles.skeletonCard}>
              <div className={styles.skeletonRow}>
                <div className={styles.skeletonAvatar} />
                <div className={styles.skeletonContent}>
                  <div className={styles.skeletonLine} />
                  <div className={styles.skeletonLineShort} />
                  <div className={styles.skeletonMeta} />
                </div>
              </div>
              <div className={styles.skeletonBar} />
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div className={styles.stateBox}>
          <div className={styles.stateIconWrap}>
            <Icon name="bell" size={28} />
          </div>
          <div className={styles.stateTitle}>Не удалось загрузить данные</div>
          <div className={styles.stateText}>{error}</div>
          <button className={styles.btnRetry} onClick={refetch}>Повторить</button>
        </div>
      )}

      {/* Loaded */}
      {!loading && !error && (
        <>
          {/* Summary strip */}
          <div className={styles.summaryBar}>
            <div className={styles.summaryItem}>
              <span className={styles.summaryNum}>{total}</span>
              <span className={styles.summaryLabel}>Активных<br />студентов</span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryNum}>{items.length || '—'}</span>
              <span className={styles.summaryLabel}>На этой<br />странице</span>
            </div>
          </div>

          {/* Empty state */}
          {items.length === 0 && (
            <div className={styles.emptyBox}>
              <div className={styles.emptyIcon}>
                <Icon name="users" size={36} />
              </div>
              <div className={styles.emptyTitle}>
                {query
                  ? `По запросу «${query}» студенты не найдены`
                  : 'Пока нет назначенных студентов'}
              </div>
              {!query && (
                <div className={styles.emptySub}>
                  Когда супервизор назначит вам студента, он появится в этом разделе.
                </div>
              )}
            </div>
          )}

          {/* Student cards */}
          {items.length > 0 && (
            <>
              <div className={styles.grid}>
                {items.map(student => (
                  <div key={student.engagement_id} className={styles.card}>
                    <div className={styles.cardTop}>
                      <div className={styles.avatar}>
                        {getInitials(student.full_name)}
                      </div>
                      <div className={styles.cardInfo}>
                        <div className={styles.fullName}>{student.full_name}</div>
                        <div className={styles.email}>{student.email}</div>
                        <div className={styles.meta}>
                          <span>Назначен {formatDate(student.assigned_at)}</span>
                          <span className={styles.badgeActive}>Активен</span>
                        </div>
                      </div>
                    </div>

                    <div className={styles.cardActions}>
                      <button
                        className={styles.actionBtn}
                        disabled
                        title="Чат будет доступен в следующих версиях"
                      >
                        <Icon name="chat" size={13} />
                        <span>Чат</span>
                        <span className={styles.soonTag}>скоро</span>
                      </button>
                      <button
                        className={styles.actionBtn}
                        disabled
                        title="Расписание будет доступно в следующих версиях"
                      >
                        <Icon name="calendar" size={13} />
                        <span>Расписание</span>
                        <span className={styles.soonTag}>скоро</span>
                      </button>
                      <Link
                        to={`/psychologist/students/${student.student_id}`}
                        className={styles.actionBtnLink}
                      >
                        <Icon name="diary" size={13} />
                        <span>Открыть карточку</span>
                      </Link>
                    </div>
                  </div>
                ))}
              </div>

              {totalPages > 1 && (
                <div className={styles.pagination}>
                  <button
                    className={styles.pageBtn}
                    disabled={page === 1}
                    onClick={() => setPage(p => p - 1)}
                  >
                    <Icon name="chevron-left" size={16} />
                  </button>
                  <span className={styles.pageInfo}>{page} / {totalPages}</span>
                  <button
                    className={styles.pageBtn}
                    disabled={page === totalPages}
                    onClick={() => setPage(p => p + 1)}
                  >
                    <Icon name="chevron-right" size={16} />
                  </button>
                </div>
              )}

              <div className={styles.totalHint}>Всего студентов: {total}</div>
            </>
          )}
        </>
      )}
    </div>
  );
}
