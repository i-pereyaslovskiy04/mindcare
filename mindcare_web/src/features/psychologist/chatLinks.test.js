import { getPsychologistStudentChatPath } from './chatLinks';

test('builds psychologist chat path with conversation query when conversation uuid exists', () => {
  expect(getPsychologistStudentChatPath({ conversation_uuid: 'conv-1', student_id: 7 }))
    .toBe('/psychologist/chat?conversation=conv-1');
});

test('builds psychologist chat path with student query fallback', () => {
  expect(getPsychologistStudentChatPath({ student_id: 7 }))
    .toBe('/psychologist/chat?student=7');
});
