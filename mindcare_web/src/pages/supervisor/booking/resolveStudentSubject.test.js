import { resolveCreatedStudentSubject } from './resolveStudentSubject';

const ENGAGEMENTS = [
  { client: { id: 10, uuid: 'uuid-a', full_name: 'Анна А.' }, psychologist: { id: 5 } },
  { client: { id: 11, uuid: 'uuid-b', full_name: 'Борис Б.' }, psychologist: { id: 7 } },
];

describe('resolveCreatedStudentSubject', () => {
  test('matches created student by uuid → subject with INT id', () => {
    const subj = resolveCreatedStudentSubject(
      { uuid: 'uuid-a', full_name: 'Анна А.' },
      ENGAGEMENTS,
      '5',
    );
    expect(subj).toEqual({ kind: 'student', id: 10, label: 'Анна А.' });
  });

  test('uses created full_name as label fallback when engagement name is empty', () => {
    const eng = [
      { client: { id: 12, uuid: 'uuid-c', full_name: '' }, psychologist: { id: 5 } },
    ];
    const subj = resolveCreatedStudentSubject(
      { uuid: 'uuid-c', full_name: 'Вера В.' },
      eng,
      5,
    );
    expect(subj.label).toBe('Вера В.');
  });

  test('returns null when no engagement matches the uuid', () => {
    expect(resolveCreatedStudentSubject({ uuid: 'nope' }, ENGAGEMENTS, 5)).toBeNull();
  });

  test('ignores an engagement that belongs to a different psychologist', () => {
    // uuid-b закреплён за психологом 7; ищем для психолога 5 → null.
    expect(resolveCreatedStudentSubject({ uuid: 'uuid-b' }, ENGAGEMENTS, 5)).toBeNull();
  });

  test('returns null on missing/invalid input', () => {
    expect(resolveCreatedStudentSubject(null, ENGAGEMENTS, 5)).toBeNull();
    expect(resolveCreatedStudentSubject({ uuid: 'uuid-a' }, null, 5)).toBeNull();
    expect(resolveCreatedStudentSubject({}, ENGAGEMENTS, 5)).toBeNull();
  });
});
