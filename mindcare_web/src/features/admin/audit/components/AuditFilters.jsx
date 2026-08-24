import { useId, useMemo } from 'react';
import Button from '../../../../components/UI/Button/Button';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import DateInput from '../../../../components/UI/DateInput';
import Select from '../../../../components/UI/Select/Select';
import { ROLE_LABELS } from '../../../../shared/lib/roles';
import AuditActorPicker from './AuditActorPicker';
import { formatDateOnly } from '../lib/auditFormatters';
import {
  ACTOR_KIND_LABELS,
  AUDIT_EVENT_LABELS,
  AUTH_EVENT_LABELS,
  ENTITY_TYPE_LABELS,
  EVENT_CATEGORY_LABELS,
  EVENT_CATEGORY_ORDER,
  OPERATION_LABELS,
  OUTCOME_LABELS,
  TABLE_LABELS,
  categoryOf,
  labelFor,
} from '../lib/auditLabels';
import {
  MAX_RECORD_REF,
  MIN_RECORD_REF,
  ORDER_OPTIONS,
  isEntityRefAllowed,
  isRecordRefAllowed,
  parseRecordRef,
} from '../lib/auditFilters';
import styles from './AuditFilters.module.css';

const ANY = { value: '', label: 'Все' };

const toOptions = (codes, map) =>
  [ANY, ...(codes ?? []).map((code) => ({ value: code, label: labelFor(map, code, code) }))];

const SUCCESS_OPTIONS = [
  { value: '', label: 'Любой' },
  { value: 'true', label: 'Успешно' },
  { value: 'false', label: 'Отказ' },
];

/** Фильтры журналов: общая часть + специфичная для активной вкладки. */
export default function AuditFilters({
  source,
  filters,
  setFilters,
  resetFilters,
  options,
  optionsError,
  onRetryOptions,
  selectedActor,
  actorResetKey,
  onSelectActor,
  onClearActor,
}) {
  const baseId = useId();
  const noRegistry = !options;

  const eventOptions = useMemo(() => {
    const codes = options?.audit_events ?? [];
    const filtered = filters.category
      ? codes.filter((code) => categoryOf(code) === filters.category)
      : codes;
    return toOptions(filtered, AUDIT_EVENT_LABELS);
  }, [options, filters.category]);

  const categoryOptions = useMemo(() => {
    const present = new Set(
      (options?.audit_events ?? []).map((code) => categoryOf(code)).filter(Boolean),
    );
    return [
      { value: '', label: 'Все категории' },
      ...EVENT_CATEGORY_ORDER
        .filter((id) => present.has(id))
        .map((id) => ({ value: id, label: EVENT_CATEGORY_LABELS[id] })),
    ];
  }, [options]);

  const kindOptions = useMemo(
    () => toOptions(options?.actor_kinds?.[source] ?? [], ACTOR_KIND_LABELS),
    [options, source],
  );

  const roleOptions = useMemo(
    () => toOptions(options?.actor_roles ?? [], ROLE_LABELS),
    [options],
  );

  const entityRefAllowed = isEntityRefAllowed(filters.entityType);
  const recordRefAllowed = isRecordRefAllowed(filters.tableName);
  const entityRef = parseRecordRef(entityRefAllowed ? filters.entityId : '');
  const recordRef = parseRecordRef(recordRefAllowed ? filters.recordId : '');

  const entityIdId = `${baseId}-entity-id`;
  const recordIdId = `${baseId}-record-id`;

  return (
    <div className={styles.panel}>
      {optionsError && (
        <div className={styles.registryError}>
          <span>
            Справочник фильтров недоступен: {optionsError}. Журнал открыт с базовыми
            фильтрами.
          </span>
          <Button type="button" variant="secondary" size="sm" onClick={onRetryOptions}>
            Загрузить справочник заново
          </Button>
        </div>
      )}

      <div className={styles.grid}>
        <div className={styles.field}>
          <DateInput
            label="С"
            value={filters.dateFrom}
            onChange={(value) => setFilters({ dateFrom: value })}
          />
        </div>

        <div className={styles.field}>
          <DateInput
            label="По"
            value={filters.dateTo}
            onChange={(value) => setFilters({ dateTo: value })}
          />
        </div>

        <AuditActorPicker
          value={selectedActor}
          resetKey={actorResetKey}
          onSelect={onSelectActor}
          onClear={onClearActor}
        />

        <Select
          label="Класс участника"
          value={filters.actorKind}
          options={kindOptions}
          disabled={noRegistry}
          onChange={(value) => setFilters({ actorKind: value })}
        />

        <Select
          label="Порядок"
          value={filters.order}
          options={ORDER_OPTIONS}
          onChange={(value) => setFilters({ order: value })}
        />

        {source === 'audit_log' && (
          <>
            <Select
              label="Категория событий"
              value={filters.category}
              options={categoryOptions}
              disabled={noRegistry}
              onChange={(value) => setFilters({ category: value })}
            />

            <div className={styles.field}>
              <Select
                label="Событие"
                value={filters.eventType}
                options={eventOptions}
                disabled={noRegistry}
                onChange={(value) => setFilters({ eventType: value })}
              />
              <span className={styles.hint}>
                Категория только сокращает список событий — сама по себе выдачу
                не фильтрует.
              </span>
            </div>

            <Select
              label="Результат"
              value={filters.outcome}
              options={toOptions(options?.outcomes, OUTCOME_LABELS)}
              disabled={noRegistry}
              onChange={(value) => setFilters({ outcome: value })}
            />

            <Select
              label="Роль действия"
              value={filters.actorRole}
              options={roleOptions}
              disabled={noRegistry}
              onChange={(value) => setFilters({ actorRole: value })}
            />

            <Select
              label="Тип объекта"
              value={filters.entityType}
              options={toOptions(options?.entity_types, ENTITY_TYPE_LABELS)}
              disabled={noRegistry}
              onChange={(value) => setFilters({ entityType: value })}
            />

            <div className={styles.field}>
              <label className={styles.label} htmlFor={entityIdId}>
                Идентификатор объекта
              </label>
              <input
                id={entityIdId}
                type="number"
                inputMode="numeric"
                className={styles.numberInput}
                min={MIN_RECORD_REF}
                max={MAX_RECORD_REF}
                step={1}
                disabled={!entityRefAllowed}
                value={filters.entityId}
                onChange={(event) => setFilters({ entityId: event.target.value })}
              />
              <span className={styles.hint}>
                {entityRefAllowed
                  ? 'Точный номер записи выбранного типа'
                  : 'Доступен после выбора типа объекта, кроме «Пользователь»'}
              </span>
              {entityRef.error && (
                <span className={styles.error} role="alert">{entityRef.error}</span>
              )}
            </div>
          </>
        )}

        {source === 'auth_log' && (
          <>
            <Select
              label="Событие"
              value={filters.event}
              options={toOptions(options?.auth_events, AUTH_EVENT_LABELS)}
              disabled={noRegistry}
              onChange={(value) => setFilters({ event: value })}
            />

            <Select
              label="Результат"
              value={filters.success === null ? '' : String(filters.success)}
              options={SUCCESS_OPTIONS}
              onChange={(value) =>
                setFilters({ success: value === '' ? null : value === 'true' })}
            />
          </>
        )}

        {source === 'data_change_log' && (
          <>
            <Select
              label="Таблица"
              value={filters.tableName}
              options={toOptions(options?.tables, TABLE_LABELS)}
              disabled={noRegistry}
              onChange={(value) => setFilters({ tableName: value })}
            />

            <Select
              label="Операция"
              value={filters.operation}
              options={toOptions(options?.operations, OPERATION_LABELS)}
              disabled={noRegistry}
              onChange={(value) => setFilters({ operation: value })}
            />

            <Select
              label="Роль действия"
              value={filters.actorRole}
              options={roleOptions}
              disabled={noRegistry}
              onChange={(value) => setFilters({ actorRole: value })}
            />

            <div className={styles.field}>
              <label className={styles.label} htmlFor={recordIdId}>
                Идентификатор записи
              </label>
              <input
                id={recordIdId}
                type="number"
                inputMode="numeric"
                className={styles.numberInput}
                min={MIN_RECORD_REF}
                max={MAX_RECORD_REF}
                step={1}
                disabled={!recordRefAllowed}
                value={filters.recordId}
                onChange={(event) => setFilters({ recordId: event.target.value })}
              />
              <span className={styles.hint}>
                {recordRefAllowed
                  ? 'Точный номер записи выбранной таблицы'
                  : 'Доступен после выбора таблицы, кроме «Пользователи»'}
              </span>
              {recordRef.error && (
                <span className={styles.error} role="alert">{recordRef.error}</span>
              )}
            </div>
          </>
        )}
      </div>

      <div className={styles.footer}>
        <span className={styles.range}>
          Период: {formatDateOnly(filters.dateFrom)} — {formatDateOnly(filters.dateTo)}
        </span>

        {source === 'audit_log' && (
          <Checkbox
            checked={filters.includeAccessEvents}
            onChange={(checked) => setFilters({ includeAccessEvents: checked })}
            label="Показывать просмотры журнала"
          />
        )}

        <Button type="button" variant="secondary" size="sm" onClick={resetFilters}>
          Сбросить фильтры
        </Button>
      </div>
    </div>
  );
}
