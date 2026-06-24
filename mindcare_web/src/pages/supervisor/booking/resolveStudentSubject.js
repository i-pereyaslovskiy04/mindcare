// Сборка subject записи для только что созданного зарегистрированного студента.
//
// POST /api/supervisor/students возвращает uuid (не числовой id), а запись требует
// student_id (INT = users.id). Создание идёт с psychologist_id, поэтому на backend
// появляется active engagement. После рефетча engagements находим студента по uuid
// и берём INT client.id — это и есть student_id для buildBookingPayload.
//
// created:     { uuid, full_name, email, ... } — ответ POST /api/supervisor/students
// engagements: [{ client: { id, uuid, full_name, email }, psychologist: { id } }]
// psychId:     выбранный психолог (string | number)
//
// Возвращает { kind: 'student', id: Number, label } либо null, если совпадение не
// найдено (например, список ещё не успел обновиться). PII не логируется.

export function resolveCreatedStudentSubject(created, engagements, psychId) {
  if (!created || !created.uuid) return null;
  if (!Array.isArray(engagements)) return null;

  const pid = Number(psychId);
  const match = engagements.find(
    (e) =>
      e?.client?.uuid === created.uuid &&
      (!pid || Number(e?.psychologist?.id) === pid)
  );
  if (!match || match.client?.id == null) return null;

  return {
    kind: 'student',
    id: Number(match.client.id),
    label:
      match.client.full_name ||
      created.full_name ||
      `Студент #${match.client.id}`,
  };
}
