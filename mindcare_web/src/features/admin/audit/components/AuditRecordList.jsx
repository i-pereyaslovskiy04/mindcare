import Button from '../../../../components/UI/Button/Button';
import { rowKey } from './rowKey';
import styles from './AuditRecordList.module.css';

const SKELETON_RECORDS = 4;

/**
 * Узкое представление журнала (< 56rem, см. AuditLogView): плотный
 * хронологический список. Модель записи общая для трёх журналов — журнал
 * отдаёт её функцией `record(item)`:
 *
 *   time, event, redacted — заголовок записи (h2: время + событие);
 *   result                — бейдж результата (может отсутствовать);
 *   actor, target         — «участник → объект» (target может отсутствовать),
 *                           подписи actorLabel / targetLabel;
 *   meta: [{ label, value }] — вторичные поля одной мелкой строкой;
 *   detailsLabel          — доступное имя кнопки «Подробнее».
 *
 * compact (≥ 39rem): «время + событие | результат | Подробнее», ниже
 * «участник → объект» и мета. mobile: то же вертикальнее — результат под
 * заголовком, участник и объект подписаны. Раскладку меняют container queries
 * в AuditRecordList.module.css; строки не кликабельны — только «Подробнее».
 */
export default function AuditRecordList({ label, items, loading, record, onOpenDetails }) {
  if (loading) {
    return (
      <ul className={styles.list} aria-label={label} aria-busy="true">
        {Array.from({ length: SKELETON_RECORDS }, (_, i) => (
          <li key={i} className={styles.skeleton}>
            <span className={styles.skeletonLine} />
            <span className={`${styles.skeletonLine} ${styles.skeletonShort}`} />
          </li>
        ))}
      </ul>
    );
  }

  return (
    <ul className={styles.list} aria-label={label}>
      {items.map((item) => {
        const r = record(item);
        return (
          <li key={rowKey(item)} className={styles.record}>
            <div className={styles.head}>
              <h2 className={styles.heading}>
                <span className={styles.time}>{r.time}</span>
                <span className="visually-hidden">, </span>
                <span className={styles.event}>{r.event}</span>
              </h2>
              {r.redacted && <p className={styles.redacted}>Часть данных скрыта</p>}
            </div>

            {r.result && <div className={styles.result}>{r.result}</div>}

            <div className={`${styles.parties}${r.target ? '' : ` ${styles.single}`}`}>
              <div className={styles.party}>
                <span className={styles.partyLabel}>{r.actorLabel ?? 'Участник'}</span>
                <div className={styles.partyValue}>{r.actor}</div>
              </div>
              {r.target && (
                <>
                  <span className={styles.arrow} aria-hidden="true">→</span>
                  <div className={styles.party}>
                    <span className={styles.partyLabel}>{r.targetLabel ?? 'Объект'}</span>
                    <div className={styles.partyValue}>{r.target}</div>
                  </div>
                </>
              )}
            </div>

            {r.meta?.length > 0 && (
              <dl className={styles.meta}>
                {r.meta.map((row) => (
                  <div key={row.label} className={styles.metaRow}>
                    <dt>{row.label}</dt>
                    <dd>{row.value}</dd>
                  </div>
                ))}
              </dl>
            )}

            <div className={styles.details}>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => onOpenDetails(item)}
                aria-label={r.detailsLabel}
              >
                Подробнее
              </Button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
