import { useState } from 'react';
import Button from '../../components/UI/Button/Button';
import { useAuth } from '../../features/auth/AuthContext';
import useStudentVerifications from '../../features/studentVerification/hooks/useStudentVerifications';
import { notifyVerificationsChanged } from '../../features/studentVerification/lib/verificationEvents';
import VerificationsTable from '../../features/studentVerification/ui/VerificationsTable';
import VerificationReviewModal from '../../features/studentVerification/ui/VerificationReviewModal';
import { lastPageOf } from '../../shared/lib/pagination';
import styles from './StudentVerificationsPage.module.css';

/** «21–40 из 1000» для текущей страницы. */
export function rangeLabel(page, pageSize, count, total) {
  if (!count) return `0 из ${total}`;
  const from = (page - 1) * pageSize + 1;
  return `${from}–${from + count - 1} из ${total}`;
}

/**
 * «Подтверждение студентов» — очередь заявок ДонГУ, ожидающих проверки
 * supervisor'ом (ADR-029): только pending, FIFO, серверная пагинация по 20,
 * без фильтров и поиска. После решения заявка уходит из очереди, total и
 * бейдж меню обновляются. Пока загружается другая страница, строки и диапазон
 * прежней не показываются (хук отдаёт pageLoading) — старые заявки нельзя
 * открыть как записи новой страницы. В режиме «под именем» раздел недоступен
 * (backend отвечает 403) — запросы не выполняются, показывается пояснение.
 */
export default function StudentVerificationsPage() {
  const { isImpersonating } = useAuth();
  const list = useStudentVerifications(!isImpersonating);
  const [openUuid, setOpenUuid] = useState(null);
  const pages = lastPageOf(list.total, list.pageSize);
  // Страница меняется сразу, а данные приходят позже: пока их нет, листать нельзя.
  const busy = list.loading || list.pageLoading;

  function refreshQueue() {
    list.refetch();
    notifyVerificationsChanged();
  }

  function handleDecided() {
    setOpenUuid(null);
    refreshQueue();
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.pageTitle}>Подтверждение студентов</h1>
          <p className={styles.sub}>
            Заявки пользователей на подтверждение статуса студента ДонГУ в порядке
            поступления. Номер студенческого билета виден только в карточке заявки.
          </p>
        </div>
      </div>

      {isImpersonating ? (
        <div className={styles.notice} role="status">
          Проверка заявок недоступна при входе под именем пользователя.
        </div>
      ) : (
        <>
          {!list.error && !list.pageLoading && (
            <div className={styles.summary} aria-live="polite">
              Ожидают проверки: <strong>{list.total}</strong>
              {list.total > 0 && (
                <span className={styles.range}>
                  {rangeLabel(list.page, list.pageSize, list.items.length, list.total)}
                </span>
              )}
            </div>
          )}

          {list.pageLoading ? (
            <div className={styles.stateBox} role="status">Загрузка заявок…</div>
          ) : list.error ? (
            <div className={styles.stateBox} role="alert">{list.error}</div>
          ) : list.items.length === 0 ? (
            <div className={styles.stateBox}>Заявок на проверке нет</div>
          ) : (
            <VerificationsTable items={list.items} onOpen={setOpenUuid} />
          )}

          {list.total > list.pageSize && (
            <nav className={styles.pagination} aria-label="Страницы очереди">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={list.page <= 1 || busy}
                onClick={() => list.setPage((p) => p - 1)}
              >
                Назад
              </Button>
              <span className={styles.pageInfo}>Страница {list.page} из {pages}</span>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={list.page >= pages || busy}
                onClick={() => list.setPage((p) => p + 1)}
              >
                Далее
              </Button>
            </nav>
          )}

          <VerificationReviewModal
            uuid={openUuid}
            onClose={() => setOpenUuid(null)}
            onDecided={handleDecided}
            onStale={refreshQueue}
          />
        </>
      )}
    </div>
  );
}
