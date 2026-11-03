// Встречи клиента в кабинете психолога: подписи и формат времени (ADR-035).
// Время — только московское через Intl (не ручной +3).

const _dateFmt = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow', day: 'numeric', month: 'long', year: 'numeric',
});
const _timeFmt = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit',
});

/** «12 октября 2026, 14:00–14:50» */
export function formatMeetingWhen(startsAt, endsAt) {
  if (!startsAt) return '—';
  const start = new Date(startsAt);
  const time = endsAt
    ? `${_timeFmt.format(start)}–${_timeFmt.format(new Date(endsAt))}`
    : _timeFmt.format(start);
  return `${_dateFmt.format(start)}, ${time}`;
}

/** Итог встречи — как в истории сессий клиента. */
export const OUTCOME_LABELS = {
  completed: 'Состоялась',
  no_show:   'Неявка',
};

export const MEETING_STATUS_LABELS = {
  pending_confirmation: 'Ожидает подтверждения',
  confirmed:            'Подтверждена',
  cancelled:            'Отменена',
  declined:             'Отклонена',
  ...OUTCOME_LABELS,
};

export const MEETING_STATUS_TONES = {
  pending_confirmation: 'warning',
  confirmed:            'success',
  cancelled:            'neutral',
  declined:             'neutral',
  completed:            'success',
  no_show:              'warning',
};

export const MODALITY_LABELS = { online: 'Онлайн', in_person: 'Очно' };

/**
 * Подпись статуса в списке. Прошедшая неподтверждённая запись слот не держит
 * и итога не получит — «Не подтверждена».
 */
export function meetingStatusLabel(item, { past = false } = {}) {
  if (past && item.status === 'pending_confirmation') return 'Не подтверждена';
  return MEETING_STATUS_LABELS[item.status] || 'Статус неизвестен';
}

export function meetingStatusTone(item, { past = false } = {}) {
  if (past && item.status === 'pending_confirmation') return 'neutral';
  return MEETING_STATUS_TONES[item.status] || 'neutral';
}
