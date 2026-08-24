import Button from '../../../../components/UI/Button/Button';
import styles from './AuditPagination.module.css';

/**
 * Пагинация журналов.
 *
 * `totalPages` приходит уже с поправкой на `max_result_window` (см.
 * `lib/auditFilters.js::computePagination`): backend ограничивает не только
 * глубину смещения, но и достижимую страницу, поэтому обычный
 * `ceil(total / size)` предлагал бы страницу, которая гарантированно вернёт 422.
 */
export default function AuditPagination({
  page, totalPages, windowLimited, maxResultWindow, onPageChange,
}) {
  if (totalPages <= 1) return null;

  return (
    <div className={styles.pagination}>
      <div className={styles.controls}>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          ← Назад
        </Button>
        <span className={styles.pageInfo}>Стр. {page} из {totalPages}</span>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Вперёд →
        </Button>
      </div>

      {windowLimited && (
        <p className={styles.limitNote}>
          Доступны первые {maxResultWindow.toLocaleString('ru-RU')} записей —
          сузьте период или фильтры.
        </p>
      )}
    </div>
  );
}
