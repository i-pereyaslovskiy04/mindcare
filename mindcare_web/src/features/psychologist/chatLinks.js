const CHAT_ROUTE = '/psychologist/chat';

function firstPresent(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== '');
}

function topLevelId(student) {
  if (!student || student.id == null || student.id === '') return null;
  if (student.engagement_id != null && String(student.id) === String(student.engagement_id)) {
    return null;
  }
  return student.id;
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
    student?.student_id,
    student?.studentId,
    student?.student?.id,
    student?.user_id,
    student?.userId,
    student?.user?.id,
    student?.client_id,
    student?.clientId,
    student?.client?.id,
    topLevelId(student),
    fallbackStudentId,
    student?.student_uuid,
    student?.studentUuid,
    student?.student?.uuid,
    student?.user_uuid,
    student?.userUuid,
    student?.user?.uuid,
    student?.client_uuid,
    student?.clientUuid,
    student?.client?.uuid,
    student?.uuid,
  );

  if (!studentId) return null;
  return `${CHAT_ROUTE}?student=${encodeURIComponent(String(studentId))}`;
}
