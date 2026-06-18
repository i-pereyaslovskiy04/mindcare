import Icon from '../../components/Icon/Icon';
import Badge from '../../components/UI/Badge/Badge';
import Button from '../../components/UI/Button/Button';
import ButtonLink from '../../components/UI/Button/ButtonLink';
import { getInitials } from '../../shared/lib/utils';
import { useMyStudents } from '../../features/psychologist/hooks/useMyStudents';
import { getPsychologistStudentChatPath } from '../../features/psychologist/chatLinks';
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
          <Button variant="secondary" onClick={refetch}>Повторить</Button>
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
                {items.map(student => {
                  const chatPath = getPsychologistStudentChatPath(student);

                  return (
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
                          <Badge tone="success">Активен</Badge>
                        </div>
                      </div>
                    </div>

                    <div className={styles.cardActions}>
                      {chatPath ? (
                        <ButtonLink
                          to={chatPath}
                          variant="ghost"
                          size="sm"
                          title="Открыть чат со студентом"
                        >
                          <Icon name="chat" size={13} />
                          <span>Чат со студентом</span>
                        </ButtonLink>
                      ) : (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled
                          title="Чат будет доступен в следующих версиях"
                        >
                          <Icon name="chat" size={13} />
                          <span>Чат</span>
                          <span className={styles.soonTag}>скоро</span>
                        </Button>
                      )}
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled
                        title="Расписание будет доступно в следующих версиях"
                      >
                        <Icon name="calendar" size={13} />
                        <span>Расписание</span>
                        <span className={styles.soonTag}>скоро</span>
                      </Button>
                      <ButtonLink
                        to={`/psychologist/students/${student.student_id}`}
                        variant="secondary"
                        size="sm"
                      >
                        <Icon name="diary" size={13} />
                        <span>Открыть карточку</span>
                      </ButtonLink>
                    </div>
                  </div>
                  );
                })}
              </div>

              {totalPages > 1 && (
                <div className={styles.pagination}>
                  <Button
                    type="button"
                    variant="icon"
                    size="sm"
                    aria-label="Предыдущая страница"
                    disabled={page === 1}
                    onClick={() => setPage(p => p - 1)}
                  >
                    <Icon name="chevron-left" size={16} />
                  </Button>
                  <span className={styles.pageInfo}>{page} / {totalPages}</span>
                  <Button
                    type="button"
                    variant="icon"
                    size="sm"
                    aria-label="Следующая страница"
                    disabled={page === totalPages}
                    onClick={() => setPage(p => p + 1)}
                  >
                    <Icon name="chevron-right" size={16} />
                  </Button>
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
