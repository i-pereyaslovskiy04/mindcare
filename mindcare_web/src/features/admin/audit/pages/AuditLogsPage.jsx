import { useState } from 'react';
import Button from '../../../../components/UI/Button/Button';
import AuditDetailsModal from '../components/AuditDetailsModal';
import AuditEventsTable from '../components/AuditEventsTable';
import AuditFilters from '../components/AuditFilters';
import AuditPagination from '../components/AuditPagination';
import AuditTabs, { tabButtonId, tabPanelId } from '../components/AuditTabs';
import AuthEventsTable from '../components/AuthEventsTable';
import DataChangesTable from '../components/DataChangesTable';
import { useAdminAuditLogs } from '../hooks/useAdminAuditLogs';
import { useAuditOptions } from '../hooks/useAuditOptions';
import { FALLBACK_LIMITS } from '../lib/auditFilters';
import { JOURNAL_LABELS } from '../lib/auditLabels';
import styles from './AuditLogsPage.module.css';

const TABS = [
  { id: 'audit_log', label: JOURNAL_LABELS.audit_log },
  { id: 'auth_log', label: JOURNAL_LABELS.auth_log },
  { id: 'data_change_log', label: JOURNAL_LABELS.data_change_log },
];

const TABLES = {
  audit_log: AuditEventsTable,
  auth_log: AuthEventsTable,
  data_change_log: DataChangesTable,
};

/**
 * Read-only просмотр трёх журналов аудита (Stage 8 UI).
 *
 * Журналы намеренно НЕ объединяются в одну ленту: у них разные контракты,
 * разные безопасные DTO и нет надёжного correlation_id между `audit_log` и
 * `data_change_log`. Три вкладки — три отдельных запроса.
 */
export default function AuditLogsPage() {
  const {
    data: options,
    error: optionsError,
    refetch: refetchOptions,
  } = useAuditOptions();

  const {
    items, loading, error, total,
    page, setPage,
    filters, setFilters, resetFilters,
    refetch, source, setSource,
    totalPages, windowLimited, maxResultWindow,
    selectedActor, selectActor, clearActor, actorResetKey,
  } = useAdminAuditLogs({
    options,
    limits: options?.limits ?? FALLBACK_LIMITS,
  });

  const [detailsItem, setDetailsItem] = useState(null);

  const Table = TABLES[source];
  const countReady = !loading && !error;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={styles.title}>Журнал действий</h1>
          {countReady && (
            <span className={styles.total}>
              {total.toLocaleString('ru-RU')} записей
            </span>
          )}
        </div>
        <Button type="button" variant="secondary" onClick={refetch}>
          Обновить
        </Button>
      </div>

      <p className={styles.note}>
        Показаны события, зафиксированные системой аудита. Это не история каждого
        перехода по страницам.
      </p>

      <AuditTabs tabs={TABS} active={source} onChange={setSource} />

      <div
        role="tabpanel"
        id={tabPanelId(source)}
        aria-labelledby={tabButtonId(source)}
        tabIndex={-1}
      >
        <AuditFilters
          source={source}
          filters={filters}
          setFilters={setFilters}
          resetFilters={resetFilters}
          options={options}
          optionsError={optionsError}
          onRetryOptions={refetchOptions}
          selectedActor={selectedActor}
          actorResetKey={actorResetKey}
          onSelectActor={selectActor}
          onClearActor={clearActor}
        />

        <Table
          items={items}
          loading={loading}
          error={error}
          onRetry={refetch}
          onOpenDetails={setDetailsItem}
        />

        {countReady && (
          <AuditPagination
            page={page}
            totalPages={totalPages}
            windowLimited={windowLimited}
            maxResultWindow={maxResultWindow}
            onPageChange={setPage}
          />
        )}
      </div>

      <AuditDetailsModal item={detailsItem} onClose={() => setDetailsItem(null)} />
    </div>
  );
}
