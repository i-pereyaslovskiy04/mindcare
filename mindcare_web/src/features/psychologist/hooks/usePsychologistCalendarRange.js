import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getPsychologistAppointments,
  getPsychologistGroupSessions,
} from '../../../api/appointments.api';
import {
  appointmentToEvent,
  groupSessionToEvent,
  groupEventsByDay,
  monthBounds,
} from '../calendar/calendarMappers';

const PAGE_SIZE = 100;

async function fetchAllAppointments({ dateFrom, dateTo, status }) {
  const first = await getPsychologistAppointments({
    page: 1, size: PAGE_SIZE, dateFrom, dateTo, status: status || undefined,
  });
  let items = first.items || [];
  const total = first.total || 0;
  let page = 2;
  while (items.length < total) {
    const next = await getPsychologistAppointments({
      page, size: PAGE_SIZE, dateFrom, dateTo, status: status || undefined,
    });
    const batch = next.items || [];
    if (batch.length === 0) break;
    items = items.concat(batch);
    page += 1;
  }
  return items;
}

async function fetchAllGroupSessions({ dateFrom, dateTo }) {
  const first = await getPsychologistGroupSessions({
    page: 1, size: PAGE_SIZE, includePast: true, dateFrom, dateTo,
  });
  let items = first.items || [];
  const total = first.total || 0;
  let page = 2;
  while (items.length < total) {
    const next = await getPsychologistGroupSessions({
      page, size: PAGE_SIZE, includePast: true, dateFrom, dateTo,
    });
    const batch = next.items || [];
    if (batch.length === 0) break;
    items = items.concat(batch);
    page += 1;
  }
  return items;
}

/**
 * Календарные данные психолога за произвольный диапазон дат.
 * Грузит ВСЕ записи диапазона (отдельно от пагинированного основного списка),
 * опционально групповые занятия. Защита от race condition через reqId.
 */
export function usePsychologistCalendarRange({
  dateFrom,
  dateTo,
  status,
  includeGroups = true,
} = {}) {
  const [appointments, setAppointments] = useState([]);
  const [groupSessions, setGroupSessions] = useState([]);
  const [eventsByDay, setEventsByDay] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const reqId = useRef(0);

  const fetchData = useCallback(async () => {
    if (!dateFrom || !dateTo) return;
    const id = ++reqId.current;
    setLoading(true);
    setError(null);
    try {
      const appts = await fetchAllAppointments({ dateFrom, dateTo, status });
      const groups = includeGroups
        ? await fetchAllGroupSessions({ dateFrom, dateTo })
        : [];
      if (id !== reqId.current) return;
      const events = [
        ...appts.map(appointmentToEvent),
        ...groups.map(groupSessionToEvent),
      ];
      setAppointments(appts);
      setGroupSessions(groups);
      setEventsByDay(groupEventsByDay(events));
    } catch (e) {
      if (id !== reqId.current) return;
      setError(e.message || 'Ошибка загрузки календаря');
    } finally {
      if (id === reqId.current) setLoading(false);
    }
  }, [dateFrom, dateTo, status, includeGroups]);

  useEffect(() => { fetchData(); }, [fetchData]);

  return {
    appointments,
    groupSessions,
    eventsByDay,
    loading,
    error,
    refetch: fetchData,
  };
}

/** Тонкая обёртка: календарь конкретного месяца (year, month 0-indexed). */
export function usePsychologistCalendarMonth({
  year,
  month,
  status,
  includeGroups = true,
} = {}) {
  const { dateFrom, dateTo } = monthBounds(year, month);
  return usePsychologistCalendarRange({
    dateFrom, dateTo, status, includeGroups,
  });
}
