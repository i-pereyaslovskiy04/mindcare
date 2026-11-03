import { useCallback } from 'react';
import { getClientAppointments } from '../../../api/appointments.api';
import useKeysetList from '../../assignments/hooks/useKeysetList';
import useAppointmentOutcome from './useAppointmentOutcome';

export const CLIENT_MEETINGS_PAGE_SIZE = 20;

// 404 при догрузке — сопровождение закрыто/передано или клиент отключён:
// уже показанные встречи очищаются, раздел «недоступен».
const isGone = (err) => err?.status === 404;

function statusOf(list) {
  if (list.loading && list.items.length === 0) return 'loading';
  if (list.error) return list.error.status === 404 ? 'unavailable' : 'error';
  return 'ready';
}

/**
 * Встречи выбранного клиента с текущим психологом (ADR-035): предстоящие и
 * история — два keyset-списка; выборку ограничивает backend (клиент И
 * психолог). Ключ — uuid клиента: при его смене прежние встречи пропадают
 * сразу, запоздалые ответы отбрасываются (generation в useKeysetList).
 * После отметки итога (и после 409/404) оба списка перечитываются.
 */
export default function useClientMeetings(studentUuid, { pageSize = CLIENT_MEETINGS_PAGE_SIZE } = {}) {
  const fetchUpcoming = useCallback(
    ({ before }) => getClientAppointments(studentUuid, { view: 'upcoming', before, size: pageSize }),
    [studentUuid, pageSize],
  );
  const fetchHistory = useCallback(
    ({ before }) => getClientAppointments(studentUuid, { view: 'history', before, size: pageSize }),
    [studentUuid, pageSize],
  );
  const options = { enabled: Boolean(studentUuid), resetKey: studentUuid, isFatalLoadMoreError: isGone };
  const upcoming = useKeysetList(fetchUpcoming, options);
  const history = useKeysetList(fetchHistory, options);

  const resetUpcoming = upcoming.reset;
  const resetHistory = history.reset;
  const reload = useCallback(() => {
    resetUpcoming();
    resetHistory();
  }, [resetUpcoming, resetHistory]);

  const outcome = useAppointmentOutcome({ onDone: reload });

  const upcomingStatus = statusOf(upcoming);
  const historyStatus = statusOf(history);
  const unavailable = upcomingStatus === 'unavailable' || historyStatus === 'unavailable';

  return {
    upcoming,
    history,
    upcomingStatus,
    historyStatus,
    status: unavailable ? 'unavailable' : 'ready',
    reload,
    outcome,
  };
}
