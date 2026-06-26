import { buildBookingPayload } from './buildBookingPayload';

const SLOT = { starts_at: '2026-06-22T10:00:00+03:00', ends_at: '2026-06-22T10:50:00+03:00' };

describe('buildBookingPayload', () => {
  test('registered student → only student_id, no card field', () => {
    const out = buildBookingPayload({
      subject: { kind: 'student', id: 123, label: 'Иванов И.' },
      psychId: '45',
      meetingTypeId: '7',
      modality: 'in_person',
      slot: SLOT,
      topic: 'тревожность',
    });
    expect(out).toEqual({
      psychologist_id: 45,
      meeting_type_id: 7,
      starts_at: SLOT.starts_at,
      modality: 'in_person',
      topic: 'тревожность',
      student_id: 123,
    });
    expect(out).not.toHaveProperty('unregistered_student_card_id');
  });

  test('unregistered card → only unregistered_student_card_id, no student field', () => {
    const out = buildBookingPayload({
      subject: { kind: 'card', id: 88, label: 'Петров П.' },
      psychId: 45,
      meetingTypeId: 7,
      modality: 'online',
      slot: SLOT,
      topic: '',
    });
    expect(out).toEqual({
      psychologist_id: 45,
      meeting_type_id: 7,
      starts_at: SLOT.starts_at,
      modality: 'online',
      topic: null,
      unregistered_student_card_id: 88,
    });
    expect(out).not.toHaveProperty('student_id');
  });

  test('newly created student (supervisor /students flow) → student_id only', () => {
    // resolveCreatedStudentSubject отдаёт { kind:'student', id:<int> }; запись
    // обрабатывает его точно так же, как обычного зарегистрированного студента.
    const out = buildBookingPayload({
      subject: { kind: 'student', id: 777, label: 'Новый Н.' },
      psychId: '5',
      meetingTypeId: '3',
      modality: 'online',
      slot: SLOT,
      topic: '',
    });
    expect(out.student_id).toBe(777);
    expect(out).not.toHaveProperty('unregistered_student_card_id');
  });

  test('never sends both subject identifiers at once', () => {
    const student = buildBookingPayload({
      subject: { kind: 'student', id: 1 },
      psychId: 2, meetingTypeId: 3, modality: 'in_person', slot: SLOT,
    });
    const card = buildBookingPayload({
      subject: { kind: 'card', id: 1 },
      psychId: 2, meetingTypeId: 3, modality: 'in_person', slot: SLOT,
    });
    expect('student_id' in student && 'unregistered_student_card_id' in student).toBe(false);
    expect('student_id' in card && 'unregistered_student_card_id' in card).toBe(false);
  });

  test('empty topic becomes null', () => {
    const out = buildBookingPayload({
      subject: { kind: 'student', id: 1 },
      psychId: 2, meetingTypeId: 3, modality: 'in_person', slot: SLOT,
    });
    expect(out.topic).toBeNull();
  });

  test('returns null when subject is missing', () => {
    expect(buildBookingPayload({
      subject: null, psychId: 2, meetingTypeId: 3, modality: 'in_person', slot: SLOT,
    })).toBeNull();
  });

  test('returns null when slot is missing', () => {
    expect(buildBookingPayload({
      subject: { kind: 'student', id: 1 },
      psychId: 2, meetingTypeId: 3, modality: 'in_person', slot: null,
    })).toBeNull();
  });

  test('returns null for unknown subject kind', () => {
    expect(buildBookingPayload({
      subject: { kind: 'mystery', id: 1 },
      psychId: 2, meetingTypeId: 3, modality: 'in_person', slot: SLOT,
    })).toBeNull();
  });
});
