import { apiFetch } from './client';

// ── Student ───────────────────────────────────────────────────────────────────

export const getMyAppointments = ({ page = 1, size = 50, status } = {}) => {
  const p = new URLSearchParams({ page, size });
  if (status) p.set('status', status);
  return apiFetch(`/api/appointments/my?${p}`);
};

// Доступные для записи индивидуальные типы встреч (выбор студентом).
export const getStudentMeetingTypes = () =>
  apiFetch('/api/appointments/meeting-types');

// Слоты требуют meeting_type_id + modality (schedule v2). Психолог берётся
// бэкендом из активного engagement студента.
export const getAvailableSlots = (date, { meetingTypeId, modality } = {}) => {
  const p = new URLSearchParams({ date });
  if (meetingTypeId != null && meetingTypeId !== '') {
    p.set('meeting_type_id', meetingTypeId);
  }
  if (modality) p.set('modality', modality);
  return apiFetch(`/api/appointments/slots?${p}`);
};

export const bookAppointment = (data) =>
  apiFetch('/api/appointments', {
    method: 'POST',
    body: JSON.stringify(data),
  });

export const cancelAppointment = (uuid, data = {}) =>
  apiFetch(`/api/appointments/${uuid}/cancel`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });

export const getGroupSessions = ({ page = 1, size = 20 } = {}) =>
  apiFetch(`/api/group-sessions?page=${page}&size=${size}`);

export const registerGroupSession = (uuid) =>
  apiFetch(`/api/group-sessions/${uuid}/register`, { method: 'POST' });

export const cancelGroupSessionRegistration = (uuid) =>
  apiFetch(`/api/group-sessions/${uuid}/register`, { method: 'DELETE' });

// ── Psychologist ──────────────────────────────────────────────────────────────

export const getPsychologistAppointments = ({
  page = 1,
  size = 20,
  dateFrom,
  dateTo,
  status,
} = {}) => {
  const p = new URLSearchParams({ page, size });
  if (dateFrom) p.set('date_from', dateFrom);
  if (dateTo) p.set('date_to', dateTo);
  if (status) p.set('status', status);
  return apiFetch(`/api/psychologist/appointments?${p}`);
};

export const getPsychologistGroupSessions = ({
  page = 1,
  size = 20,
  includePast = false,
  dateFrom,
  dateTo,
} = {}) => {
  const p = new URLSearchParams({ page, size, include_past: includePast });
  if (dateFrom) p.set('date_from', dateFrom);
  if (dateTo) p.set('date_to', dateTo);
  return apiFetch(`/api/psychologist/group-sessions?${p}`);
};

// Своё расписание психолога (read-only): активные rules + breaks + типы.
export const getPsychologistSchedule = () =>
  apiFetch('/api/psychologist/schedule');

export const confirmAppointment = (uuid) =>
  apiFetch(`/api/psychologist/appointments/${uuid}/confirm`, { method: 'PATCH' });

export const declineAppointment = (uuid, data = {}) =>
  apiFetch(`/api/psychologist/appointments/${uuid}/decline`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });

// ── Supervisor ────────────────────────────────────────────────────────────────

export const getMeetingTypes = () =>
  apiFetch('/api/supervisor/meeting-types');

export const createMeetingType = (data) =>
  apiFetch('/api/supervisor/meeting-types', {
    method: 'POST',
    body: JSON.stringify(data),
  });

export const updateMeetingType = (id, data) =>
  apiFetch(`/api/supervisor/meeting-types/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });

export const getScheduleRules = ({ psychologistId, includeInactive } = {}) => {
  const p = new URLSearchParams();
  if (psychologistId) p.set('psychologist_id', psychologistId);
  if (includeInactive) p.set('include_inactive', 'true');
  return apiFetch(`/api/supervisor/schedule-rules?${p}`);
};

export const deleteScheduleRule = (id) =>
  apiFetch(`/api/supervisor/schedule-rules/${id}`, { method: 'DELETE' });

export const createScheduleException = (data) =>
  apiFetch('/api/supervisor/schedule-exceptions', {
    method: 'POST',
    body: JSON.stringify(data),
  });

export const getScheduleExceptions = ({ psychologistId, dateFrom, dateTo } = {}) => {
  const p = new URLSearchParams();
  if (psychologistId) p.set('psychologist_id', psychologistId);
  if (dateFrom) p.set('date_from', dateFrom);
  if (dateTo) p.set('date_to', dateTo);
  return apiFetch(`/api/supervisor/schedule-exceptions?${p}`);
};

export const getPsychologistScheduleExceptions = ({ dateFrom, dateTo } = {}) => {
  const p = new URLSearchParams();
  if (dateFrom) p.set('date_from', dateFrom);
  if (dateTo) p.set('date_to', dateTo);
  return apiFetch(`/api/psychologist/schedule-exceptions?${p}`);
};

// ── Schedule series (schedule v2) ─────────────────────────────────────────────

export const getScheduleBreaks = ({ psychologistId } = {}) => {
  const p = new URLSearchParams();
  if (psychologistId) p.set('psychologist_id', psychologistId);
  return apiFetch(`/api/supervisor/schedule-breaks?${p}`);
};

export const createSchedule = (data) =>
  apiFetch('/api/supervisor/schedules', {
    method: 'POST',
    body: JSON.stringify(data),
  });

export const updateSchedule = (seriesId, data) =>
  apiFetch(`/api/supervisor/schedules/${seriesId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });

export const getScheduleImpact = (seriesId) =>
  apiFetch(`/api/supervisor/schedules/${seriesId}/impact`);

export const deleteSchedule = (seriesId) =>
  apiFetch(`/api/supervisor/schedules/${seriesId}`, { method: 'DELETE' });

export const restoreSchedule = (seriesId) =>
  apiFetch(`/api/supervisor/schedules/${seriesId}/restore`, { method: 'POST' });

export const extendSchedule = (seriesId, months = 1) =>
  apiFetch(`/api/supervisor/schedules/${seriesId}/extend?months=${months}`, {
    method: 'POST',
  });

// Свободные слоты психолога (для ручной записи студента супервизором).
export const getSupervisorSlots = ({
  psychologistId, date, meetingTypeId, modality,
} = {}) => {
  const p = new URLSearchParams({ psychologist_id: psychologistId, date });
  if (meetingTypeId != null && meetingTypeId !== '') {
    p.set('meeting_type_id', meetingTypeId);
  }
  if (modality) p.set('modality', modality);
  return apiFetch(`/api/supervisor/slots?${p}`);
};

export const supervisorBookAppointment = (data) =>
  apiFetch('/api/supervisor/appointments', {
    method: 'POST',
    body: JSON.stringify(data),
  });

export const getSupervisorPsychologists = () =>
  apiFetch('/api/supervisor/psychologists?size=200');

export const getSupervisorGroupSessions = ({ page = 1, size = 20 } = {}) =>
  apiFetch(`/api/supervisor/group-sessions?page=${page}&size=${size}`);

export const createGroupSession = (data) =>
  apiFetch('/api/supervisor/group-sessions', {
    method: 'POST',
    body: JSON.stringify(data),
  });

export const updateGroupSession = (uuid, data) =>
  apiFetch(`/api/supervisor/group-sessions/${uuid}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });

export const setGroupSessionBooking = (uuid, enabled) =>
  apiFetch(`/api/supervisor/group-sessions/${uuid}/booking?enabled=${enabled}`, {
    method: 'PATCH',
  });
