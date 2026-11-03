import Button from '../../../../components/UI/Button/Button';
import AuditTableShell from './AuditTableShell';
import AuditRecordList from './AuditRecordList';
import styles from './AuditLogView.module.css';

/**
 * Адаптивный слой журналов аудита — специализированная система, а не shared
 * ResponsiveTable: у журнала своя модель строки (время → событие → участник →
 * объект → результат), три разные схемы, окно выдачи и подробности.
 *
 *   ≥ 56rem — AuditTableShell: плотная семантическая таблица;
 *   < 56rem — AuditRecordList: хронологический список (compact ≥ 39rem,
 *             mobile ниже). Границы — общий стандарт таблиц MindCare.
 *
 * Журнал передаёт: `columns` (таблица), `record(item)` (запись списка) и
 * `detailsLabel(item)`. Обе раскладки в DOM, скрытая — display: none (вне
 * дерева доступности); переключение ширины не делает запросов. Ошибка (с
 * «Повторить») и пустая выдача показываются один раз, вне обеих раскладок.
 */
export default function AuditLogView({
  caption, columns, record, items, loading, error, emptyText, onRetry, onOpenDetails,
}) {
  if (!loading && error) {
    return (
      <div className={styles.state}>
        <p className={styles.errorText}>{error}</p>
        {onRetry && (
          <Button type="button" variant="secondary" size="sm" onClick={onRetry}>
            Повторить
          </Button>
        )}
      </div>
    );
  }

  if (!loading && items.length === 0) {
    return <div className={styles.state}>{emptyText}</div>;
  }

  const detailsLabel = (item) => record(item).detailsLabel;

  return (
    <div className={styles.root}>
      <div className={styles.wide}>
        <AuditTableShell
          caption={caption}
          columns={columns}
          items={items}
          loading={loading}
          detailsLabel={detailsLabel}
          onOpenDetails={onOpenDetails}
        />
      </div>
      <div className={styles.list}>
        <AuditRecordList
          label={caption}
          items={items}
          loading={loading}
          record={record}
          onOpenDetails={onOpenDetails}
        />
      </div>
    </div>
  );
}
