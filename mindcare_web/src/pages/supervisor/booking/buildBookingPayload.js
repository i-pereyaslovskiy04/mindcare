// Сборка тела запроса для POST /api/supervisor/appointments.
//
// Backend требует РОВНО один субъект записи: либо student_id (зарегистрированный
// студент с active engagement), либо unregistered_student_card_id (карточка
// пришедшего лично студента). Этот хелпер изолирует правило взаимного исключения,
// чтобы его можно было покрыть unit-тестом отдельно от UI.
//
// subject: { kind: 'student' | 'card', id, label? }
// slot:    { starts_at, ... }
//
// Возвращает payload-объект или null, если субъект/слот не выбраны.

export function buildBookingPayload({
  subject,
  psychId,
  meetingTypeId,
  modality,
  slot,
  topic,
} = {}) {
  if (!subject || !subject.kind || subject.id == null) return null;
  if (!slot || !slot.starts_at) return null;

  const base = {
    psychologist_id: Number(psychId),
    meeting_type_id: Number(meetingTypeId),
    starts_at: slot.starts_at,
    modality,
    topic: topic ? topic : null,
  };

  if (subject.kind === 'student') {
    return { ...base, student_id: Number(subject.id) };
  }
  if (subject.kind === 'card') {
    return { ...base, unregistered_student_card_id: Number(subject.id) };
  }
  return null;
}
