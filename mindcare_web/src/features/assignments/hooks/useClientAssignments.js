import { useCallback, useRef, useState } from 'react';
import { cancelAssignment, getClientAssignments } from '../../../api/assignments.api';
import useAssignmentCreate from './useAssignmentCreate';
import useKeysetList from './useKeysetList';

export const CLIENT_ASSIGNMENTS_PAGE_SIZE = 20;

const CANCEL_FALLBACK = 'Не удалось отменить задание. Повторите попытку.';
const AUDIT_UNAVAILABLE = 'Операция не зафиксирована в журнале и не выполнена. Повторите попытку позже.';

// 404 при догрузке — сопровождение закрыто/передано или клиент отключён:
// уже показанные задания больше не принадлежат доступному списку, раздел
// очищается и становится «недоступен». Прочие сбои догрузки (сеть, 5xx,
// 503 аудита) — нефатальные: загруженное остаётся, догрузку можно повторить.
const isListGone = (err) => err?.status === 404;

/** Статус раздела по ошибке списка (первая страница или фатальная догрузка). */
export function listStatus(list) {
  if (list.loading && list.items.length === 0) return 'loading';
  if (list.error) {
    if (list.error.status === 404) return 'unavailable';
    if (list.error.status === 503) return 'auditUnavailable';
    return 'error';
  }
  return 'ready';
}

/**
 * Задания клиента в карточке психолога (текущее строгое сопровождение).
 *
 * Список — keyset (loadMore); после создания, отмены, 409 и 404 (связь
 * закрыта/передана) он сбрасывается и грузится с первой страницы, устаревшие
 * ответы отбрасываются (generation). 404 догрузки очищает данные и переводит
 * раздел в 'unavailable'; сетевая ошибка догрузки — list.loadMoreError. Ключ — uuid клиента: при смене клиента
 * прежние задания пропадают сразу.
 *
 * Двойная отправка исключена ref-lock'ом: повторный create/cancel во время
 * запроса игнорируется. Чтение списка фиксируется backend'ом в журнале
 * (503 — тексты не получены).
 */
export default function useClientAssignments(studentUuid, { pageSize = CLIENT_ASSIGNMENTS_PAGE_SIZE } = {}) {
  const fetchPage = useCallback(
    ({ before }) => getClientAssignments(studentUuid, { before, size: pageSize }),
    [studentUuid, pageSize],
  );
  const list = useKeysetList(fetchPage, {
    enabled: Boolean(studentUuid), resetKey: studentUuid, isFatalLoadMoreError: isListGone,
  });

  const [pendingUuid, setPendingUuid] = useState(null);
  const [actionError, setActionError] = useState(null); // { uuid, message }
  const cancelLock = useRef(false);

  const reload = list.reset;
  // Создание — общий hook (тот же, что у быстрого действия в списке студентов).
  const { create, submitting, formError, clearFormError } = useAssignmentCreate(
    studentUuid, { onCreated: reload, onUnavailable: reload },
  );

  const cancel = useCallback(async (uuid) => {
    if (cancelLock.current) return false;
    cancelLock.current = true;
    setPendingUuid(uuid);
    setActionError(null);
    try {
      await cancelAssignment(uuid);
      reload();
      return true;
    } catch (err) {
      if (err?.status === 409) {
        setActionError({ uuid, message: 'Задание уже выполнено клиентом - отменить нельзя.' });
        reload();
      } else if (err?.status === 404) {
        setActionError({ uuid, message: 'Задание недоступно: сопровождение завершено или передано.' });
        reload();
      } else if (err?.status === 503) {
        setActionError({ uuid, message: AUDIT_UNAVAILABLE });
      } else {
        setActionError({ uuid, message: CANCEL_FALLBACK });
      }
      return false;
    } finally {
      cancelLock.current = false;
      setPendingUuid(null);
    }
  }, [reload]);

  return {
    list,
    status: listStatus(list),
    reload,
    create,
    submitting,
    formError,
    clearFormError,
    cancel,
    pendingUuid,
    actionError,
  };
}
