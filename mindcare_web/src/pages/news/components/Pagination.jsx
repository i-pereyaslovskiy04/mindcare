import styles from './NewsPage.module.css';

const MAX_VISIBLE = 5;

function getPageNumbers(page, totalPages) {
  if (totalPages <= MAX_VISIBLE) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const half = Math.floor(MAX_VISIBLE / 2);
  let start = Math.max(1, page - half);
  let end = start + MAX_VISIBLE - 1;
  if (end > totalPages) {
    end = totalPages;
    start = end - MAX_VISIBLE + 1;
  }
  return Array.from({ length: end - start + 1 }, (_, i) => start + i);
}

export default function Pagination({ page, totalPages, onPage }) {
  const pages = getPageNumbers(page, totalPages);
  const showLeadingEllipsis = pages[0] > 2;
  const showTrailingEllipsis = pages[pages.length - 1] < totalPages - 1;

  return (
    <nav className={styles.pagination} aria-label="Навигация по страницам">
      <button
        className={styles.paginBtn}
        onClick={() => onPage(page - 1)}
        disabled={page === 1}
        aria-label="Предыдущая страница"
      >
        ← Назад
      </button>

      <div className={styles.paginNumbers}>
        {pages[0] > 1 && (
          <>
            <button className={styles.paginNum} onClick={() => onPage(1)}>1</button>
            {showLeadingEllipsis && <span className={styles.paginEllipsis}>…</span>}
          </>
        )}

        {pages.map((p) => (
          <button
            key={p}
            className={`${styles.paginNum} ${p === page ? styles.paginNumActive : ''}`}
            onClick={() => onPage(p)}
            aria-current={p === page ? 'page' : undefined}
          >
            {p}
          </button>
        ))}

        {pages[pages.length - 1] < totalPages && (
          <>
            {showTrailingEllipsis && <span className={styles.paginEllipsis}>…</span>}
            <button
              className={styles.paginNum}
              onClick={() => onPage(totalPages)}
            >
              {totalPages}
            </button>
          </>
        )}
      </div>

      <button
        className={styles.paginBtn}
        onClick={() => onPage(page + 1)}
        disabled={page === totalPages}
        aria-label="Следующая страница"
      >
        Вперёд →
      </button>
    </nav>
  );
}
