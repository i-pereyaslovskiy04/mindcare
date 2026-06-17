import { getPsychologistStudentChatPath } from './chatLinks';

test('builds psychologist chat path with conversation query when conversation uuid exists', () => {
  expect(getPsychologistStudentChatPath({ conversation_uuid: 'conv-1', student_id: 7 }))
    .toBe('/psychologist/chat?conversation=conv-1');
});

test('builds psychologist chat path with student query fallback', () => {
  expect(getPsychologistStudentChatPath({ student_id: 7 }))
    .toBe('/psychologist/chat?student=7');
});

test('uses numeric student_id before student_uuid because chat DTO exposes student.id', () => {
  expect(getPsychologistStudentChatPath({
    engagement_id: 11,
    student_id: 7,
    student_uuid: 'student-uuid-7',
  })).toBe('/psychologist/chat?student=7');
});

test('does not use top-level id when it matches engagement_id', () => {
  expect(getPsychologistStudentChatPath({
    id: 11,
    engagement_id: 11,
    student_uuid: 'student-uuid-7',
  })).toBe('/psychologist/chat?student=student-uuid-7');
});

test('uses nested student id from card-shaped data', () => {
  expect(getPsychologistStudentChatPath({
    engagement_id: 11,
    student: { id: 7, uuid: 'student-uuid-7' },
  })).toBe('/psychologist/chat?student=7');
});
