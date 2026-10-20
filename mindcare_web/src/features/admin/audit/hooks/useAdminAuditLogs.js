import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AUDIT_LOADERS } from '../../../../api/audit.api';
import {
  FALLBACK_LIMITS,
  buildQuery,
  computePagination,
  defaultBySource,
  defaultCommon,
  pruneEventForCategory,
  routeFilterPatch,
  validateWindow,
} from '../lib/auditFilters';

/**
 * Список строк одного журнала аудита.
 *
 * Справочник передаётся аргументом, а не запрашивается внутри: так однозначно
 * видно, откуда берутся `max_page_size`, `max_result_window` и допустимые
 * `actor_kind`, и ошибки двух запросов остаются раздельными.
 *
 *   useAdminAuditLogs({ options, limits: options?.limits ?? FALLBACK_LIMITS })
 *
 * Фильтры хранятся ПО ЖУРНАЛАМ (см. `lib/auditFilters.js`): переключение вкладки
 * не может унести чужое значение и получить 422.
 *
 * Выбранный участник тоже живёт здесь, а не в picker'е — иначе controlled-picker
 * не смог бы очиститься одним изменением `actorUuid`, и подпись оставалась бы
 * висеть после сброса фильтров.
 */
export function useAdminAuditLogs({ options = null, limits = FALLBACK_LIMITS } = {}) {
  const pageSize = limits?.default_page_size ?? FALLBACK_LIMITS.default_page_size;
  const maxRangeDays = limits?.max_range_days ?? FALLBACK_LIMITS.max_range_days;
  const maxResultWindow =
    limits?.max_result_window ?? FALLBACK_LIMITS.max_result_window;
  const defaultRangeDays =
    limits?.default_range_days ?? FALLBACK_LIMITS.default_range_days;

  const [source, setSourceRaw] = useState('audit_log');
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [tick, setTick] = useState(0);

  // Окно инициализируется один раз по fallback-значению: подтянувшийся позже
  // справочник не должен молча переопределять уже показанный пользователю
  // период.
  const [common, setCommon] = useState(() =>
    defaultCommon(FALLBACK_LIMITS.default_range_days),
  );
  const [bySource, setBySource] = useState(defaultBySource);

  const [selectedActor, setSelectedActor] = useState(null);
  const [actorResetKey, setActorResetKey] = useState(0);

  // `query` существует ради общего контракта admin-списков. Свободного поиска у
  // журналов нет — участник адресуется точным UUID, — поэтому значение никуда
  // не отправляется.
  const [query, setQuery] = useState('');

  // Справочник читается из ref, а не из зависимостей эффекта: его загрузка не
  // должна вызывать второй запрос списка. Значение `actor_kind` без справочника
  // выставить нельзя (селект отключён), поэтому запрос от этого не меняется.
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const slice = bySource[source];

  const windowError = useMemo(
    () => validateWindow(common.dateFrom, common.dateTo, maxRangeDays),
    [common.dateFrom, common.dateTo, maxRangeDays],
  );

  const latest = useRef(0);

  useEffect(() => {
    if (windowError) {
      latest.current += 1;
      setItems([]);
      setTotal(0);
      setLoading(false);
      setError(windowError);
      return undefined;
    }

    let cancelled = false;
    const reqId = latest.current + 1;
    latest.current = reqId;

    setLoading(true);
    setError(null);

    const load = AUDIT_LOADERS[source];
    load(buildQuery({
      source,
      common,
      slice,
      page,
      size: pageSize,
      options: optionsRef.current,
    }))
      .then((data) => {
        if (cancelled || latest.current !== reqId) return;
        setItems(data?.items ?? []);
        setTotal(data?.total ?? 0);
      })
      .catch((err) => {
        if (cancelled || latest.current !== reqId) return;
        setItems([]);
        setTotal(0);
        setError(err.message);
      })
      .finally(() => {
        if (cancelled || latest.current !== reqId) return;
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [source, common, slice, page, pageSize, tick, windowError]);

  // Сравнение через ref, а не внутри updater'а: функция обновления состояния
  // обязана быть чистой (React может вызвать её дважды).
  const sourceRef = useRef(source);
  sourceRef.current = source;

  const setSource = useCallback((next) => {
    if (sourceRef.current === next) return;
    sourceRef.current = next;
    // Данные предыдущего журнала не должны ни секунды выдаваться за текущие.
    setItems([]);
    setTotal(0);
    setPage(1);
    setSourceRaw(next);
  }, []);

  const clearActor = useCallback(() => {
    setSelectedActor(null);
    setCommon((prev) => (prev.actorUuid ? { ...prev, actorUuid: '' } : prev));
    setActorResetKey((k) => k + 1);
    setPage(1);
  }, []);

  const selectActor = useCallback((actor) => {
    if (!actor?.uuid) return;
    setSelectedActor({
      uuid: actor.uuid,
      fullName: actor.fullName,
      emailMasked: actor.emailMasked,
      isDeleted: Boolean(actor.isDeleted),
    });
    setCommon((prev) => ({ ...prev, actorUuid: actor.uuid }));
    setPage(1);
  }, []);

  const setFilters = useCallback((patch) => {
    const routed = routeFilterPatch(patch, source);

    if (process.env.NODE_ENV !== 'production' && routed.ignored.length) {
      // eslint-disable-next-line no-console
      console.warn(
        `[audit] фильтры вне журнала ${source} отброшены: ${routed.ignored.join(', ')}`,
      );
    }

    if (Object.keys(routed.common).length) {
      setCommon((prev) => ({ ...prev, ...routed.common }));
      // Идентификатор и подпись участника обязаны быть согласованы: снятый
      // uuid не может оставить на экране выбранного человека.
      if ('actorUuid' in routed.common) {
        const next = routed.common.actorUuid;
        setSelectedActor((prevActor) =>
          next && prevActor?.uuid === next ? prevActor : null,
        );
        if (!next) setActorResetKey((k) => k + 1);
      }
    }

    if (Object.keys(routed.slice).length) {
      setBySource((prev) => {
        const current = prev[source];
        const next = { ...current, ...routed.slice };

        // Событие вне выбранной категории не должно молча уехать в запрос.
        if ('category' in routed.slice) {
          next.eventType = pruneEventForCategory(next.eventType, next.category);
        }
        // Точный идентификатор осмыслен только вместе со своим типом цели:
        // при смене типа старый номер сбрасывается. Явный номер в ТОМ ЖЕ
        // патче — это осознанный выбор вызывающего, и он не затирается.
        if (
          'entityType' in routed.slice
          && routed.slice.entityType !== current.entityType
          && !('entityId' in routed.slice)
        ) {
          next.entityId = '';
        }
        if (
          'tableName' in routed.slice
          && routed.slice.tableName !== current.tableName
          && !('recordId' in routed.slice)
        ) {
          next.recordId = '';
        }

        return { ...prev, [source]: next };
      });
    }

    setPage(1);
  }, [source]);

  const resetFilters = useCallback(() => {
    setCommon(defaultCommon(defaultRangeDays));
    setBySource(defaultBySource());
    setSelectedActor(null);
    setActorResetKey((k) => k + 1);
    setPage(1);
  }, [defaultRangeDays]);

  // Ручное обновление намеренно не трогает ни фильтры, ни страницу.
  const refetch = useCallback(() => setTick((t) => t + 1), []);

  const filters = useMemo(() => ({ ...common, ...slice }), [common, slice]);

  const { totalPages, windowLimited } = useMemo(
    () => computePagination(total, pageSize, maxResultWindow),
    [total, pageSize, maxResultWindow],
  );

  return {
    items,
    loading,
    error,
    total,
    page,
    setPage,
    query,
    setQuery,
    filters,
    setFilters,
    refetch,

    size: pageSize,
    source,
    setSource,
    resetFilters,
    totalPages,
    windowLimited,
    maxResultWindow,

    selectedActor,
    selectActor,
    clearActor,
    actorResetKey,
  };
}
