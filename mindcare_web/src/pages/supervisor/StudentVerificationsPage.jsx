import { useState } from 'react';
import Button from '../../components/UI/Button/Button';
import FilterChip from '../../components/UI/FilterChip/FilterChip';
import Icon from '../../components/Icon/Icon';
import { useAuth } from '../../features/auth/AuthContext';
import useStudentVerifications from '../../features/studentVerification/hooks/useStudentVerifications';
import VerificationsTable from '../../features/studentVerification/ui/VerificationsTable';
import VerificationReviewModal from '../../features/studentVerification/ui/VerificationReviewModal';
import styles from './StudentVerificationsPage.module.css';

const STATUS_FILTERS = [
  { value: 'pending',  label: 'На проверке' },
  { value: 'approved', label: 'Подтверждено' },
  { value: 'rejected', label: 'Отклонено' },
  { value: 'all',      label: 'Все' },
];

/**
 * «Подтверждение студентов» — проверка заявок ДонГУ supervisor'ом (ADR-029).
 * В режиме «под именем» раздел недоступен (backend отвечает 403) — запросы не
 * выполняются, показывается пояснение.
 */
export default function StudentVerificationsPage() {
  const { isImpersonating } = useAuth();
  const list = useStudentVerifications(!isImpersonating);
  const [openUuid, setOpenUuid] = useState(null);
  const pages = Math.max(1, Math.ceil(list.total / list.pageSize));

  function handleDecided() {
    setOpenUuid(null);
    list.refetch();
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <span className={styles.labelTag}>Супервизия</span>
          <h1 className={styles.pageTitle}>Подтверждение студентов</h1>
          <p className={styles.sub}>
            Заявки пользователей на подтверждение статуса студента ДонГУ.
            Номер студенческого билета виден только в карточке заявки.
          </p>
        </div>
      </div>

      {isImpersonating ? (
        <div className={styles.notice} role="status">
          Проверка заявок недоступна при входе под именем пользователя.
        </div>
      ) : (
        <>
          <div className={styles.toolbar}>
            <div className={styles.chips} role="group" aria-label="Статус заявки">
              {STATUS_FILTERS.map((f) => (
                <FilterChip
                  key={f.value}
                  active={list.filters.status === f.value}
                  onClick={() => list.setFilters({ status: f.value })}
                >
                  {f.label}
                </FilterChip>
              ))}
            </div>
            <label className={styles.searchWrap}>
              <Icon name="search" size={14} />
              <input
                className={styles.searchInput}
                type="search"
                value={list.query}
                onChange={(e) => list.setQuery(e.target.value)}
                placeholder="Поиск по ФИО или email"
                aria-label="Поиск по ФИО или email"
                maxLength={200}
              />
            </label>
          </div>

          {list.loading ? (
            <div className={styles.stateBox}>Загрузка…</div>
          ) : list.error ? (
            <div className={styles.stateBox} role="alert">{list.error}</div>
          ) : list.items.length === 0 ? (
            <div className={styles.stateBox}>Заявок нет</div>
          ) : (
            <VerificationsTable items={list.items} onOpen={setOpenUuid} />
          )}

          {list.total > list.pageSize && (
            <div className={styles.pagination}>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={list.page <= 1}
                onClick={() => list.setPage((p) => p - 1)}
              >
                Назад
              </Button>
              <span className={styles.pageInfo}>{list.page} / {pages}</span>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={list.page >= pages}
                onClick={() => list.setPage((p) => p + 1)}
              >
                Далее
              </Button>
            </div>
          )}

          <VerificationReviewModal
            uuid={openUuid}
            onClose={() => setOpenUuid(null)}
            onDecided={handleDecided}
          />
        </>
      )}
    </div>
  );
}
