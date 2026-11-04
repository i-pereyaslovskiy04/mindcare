import {
  buildSubmitBody, clearDraft, emptyDraft, loadDraft, saveDraft,
  unansweredQuestions, validateProfile,
} from './draft';

const campaign = {
  consent: { version: 2 },
  questions: [
    { id: 10, options: [{ id: 101 }, { id: 102 }] },
    { id: 11, options: [{ id: 111 }, { id: 112 }] },
  ],
};

function filled(overrides = {}) {
  return {
    ...emptyDraft(),
    fullName: '  Иванова   Мария  ',
    facultyCode: 'law',
    specialty: ' Юриспруденция ',
    age: '18',
    gender: 'female',
    consentAccepted: true,
    answers: { 10: 101, 11: 112 },
    ...overrides,
  };
}

beforeEach(() => window.sessionStorage.clear());

test('новый черновик — уникальный submissionKey', () => {
  expect(emptyDraft().submissionKey).not.toEqual(emptyDraft().submissionKey);
});

test('черновик переживает перезагрузку и удаляется после отправки', () => {
  const d = filled();
  saveDraft('tok', d);
  expect(loadDraft('tok')).toEqual(d);
  clearDraft('tok');
  expect(loadDraft('tok').fullName).toBe('');
});

test('испорченный черновик — пустой', () => {
  window.sessionStorage.setItem('mindcare.campaign.draft.tok', '{oops');
  expect(loadDraft('tok').answers).toEqual({});
});

test('проверка анкеты', () => {
  expect(validateProfile(filled())).toEqual({});
  const errors = validateProfile(filled({
    fullName: ' ', facultyCode: '', specialty: '', age: '13', gender: '',
    consentAccepted: false,
  }));
  expect(Object.keys(errors).sort()).toEqual(
    ['age', 'consent', 'facultyCode', 'fullName', 'gender', 'specialty'],
  );
  expect(validateProfile(filled({ age: '18.5' })).age).toBeDefined();
  expect(validateProfile(filled({ age: '101' })).age).toBeDefined();
});

test('пропущенные вопросы — по порядку анкеты, чужой вариант не считается', () => {
  expect(unansweredQuestions(filled({ answers: { 11: 101 } }), campaign.questions))
    .toEqual([10, 11]);
  expect(unansweredQuestions(filled(), campaign.questions)).toEqual([]);
});

test('тело отправки — нормализованные поля, версия согласия, ответы', () => {
  const d = filled();
  expect(buildSubmitBody(d, campaign)).toEqual({
    submission_key: d.submissionKey,
    full_name: 'Иванова Мария',
    faculty_code: 'law',
    specialty: 'Юриспруденция',
    age: 18,
    gender: 'female',
    consent_accepted: true,
    consent_version: 2,
    answers: [
      { question_id: 10, option_id: 101 },
      { question_id: 11, option_id: 112 },
    ],
  });
});
