const CHAT_ROUTE = '/psychologist/chat';

function firstPresent(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== '');
}

export function getPsychologistStudentChatPath(student, fallbackStudentId) {
  const conversationUuid = firstPresent(
    student?.conversation_uuid,
    student?.conversationUuid,
    student?.conversation?.uuid,
  );

  if (conversationUuid) {
    return `${CHAT_ROUTE}?conversation=${encodeURIComponent(String(conversationUuid))}`;
  }

  const studentId = firstPresent(
    student?.student_uuid,
    student?.studentUuid,
    student?.uuid,
    student?.student_id,
    student?.id,
    fallbackStudentId,
  );

  if (!studentId) return null;
  return `${CHAT_ROUTE}?student=${encodeURIComponent(String(studentId))}`;
}
