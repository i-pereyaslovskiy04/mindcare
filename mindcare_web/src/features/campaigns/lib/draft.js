/**
 * Черновик анкеты кампании (ADR-036) — чистые функции.
 *
 * Черновик живёт в sessionStorage этой вкладки (переживает F5, исчезает с
 * закрытием вкладки) и удаляется после успешной отправки. submission_key
 * создаётся один раз на черновик: повторная отправка того же черновика не
 * создаёт дубль (backend отвечает 200).
 */

const KEY_PREFIX = 'mindcare.campaign.draft.';
export const AGE_MIN = 14;
export const AGE_MAX = 100;

function newKey() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // Fallback: UUID v4 из Math.random (старые браузеры).
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.floor(Math.random() * 16);
    return (c === 'x' ? r : ((r % 4) + 8)).toString(16);
  });
}

export function emptyDraft() {
  return {
    submissionKey: newKey(),
    fullName: '',
    facultyCode: '',
    specialty: '',
    age: '',
    gender: '',
    consentAccepted: false,
    answers: {},          // { [questionId]: optionId }
  };
}

function storage() {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null;
  } catch {
    return null;
  }
}

export function loadDraft(token) {
  const raw = storage()?.getItem(KEY_PREFIX + token);
  if (!raw) return emptyDraft();
  try {
    const parsed = JSON.parse(raw);
    const base = emptyDraft();
    if (!parsed || typeof parsed !== 'object') return base;
    return {
      ...base,
      ...parsed,
      submissionKey: typeof parsed.submissionKey === 'string' && parsed.submissionKey
        ? parsed.submissionKey : base.submissionKey,
      answers: parsed.answers && typeof parsed.answers === 'object' ? parsed.answers : {},
    };
  } catch {
    return emptyDraft();
  }
}

export function saveDraft(token, draft) {
  try {
    storage()?.setItem(KEY_PREFIX + token, JSON.stringify(draft));
  } catch {
    // Переполнение/запрет хранилища — черновик просто не переживёт F5.
  }
}

export function clearDraft(token) {
  try {
    storage()?.removeItem(KEY_PREFIX + token);
  } catch {
    // ignore
  }
}

const clean = (s) => String(s ?? '').split(/\s+/).filter(Boolean).join(' ');

/** Ошибки анкеты: { fullName, facultyCode, specialty, age, gender, consent }. */
export function validateProfile(draft) {
  const errors = {};
  if (clean(draft.fullName).length < 2) errors.fullName = 'Укажите фамилию, имя и отчество';
  if (!draft.facultyCode) errors.facultyCode = 'Выберите факультет';
  if (clean(draft.specialty).length < 2) errors.specialty = 'Укажите специальность';
  const age = Number(draft.age);
  if (!/^\d+$/.test(String(draft.age).trim()) || age < AGE_MIN || age > AGE_MAX) {
    errors.age = `Возраст — целое число от ${AGE_MIN} до ${AGE_MAX}`;
  }
  if (draft.gender !== 'male' && draft.gender !== 'female') errors.gender = 'Укажите пол';
  if (!draft.consentAccepted) errors.consent = 'Без согласия пройти тестирование нельзя';
  return errors;
}

/** id вопросов без ответа, в порядке анкеты. */
export function unansweredQuestions(draft, questions) {
  return questions
    .filter((q) => !q.options.some((o) => o.id === draft.answers[q.id]))
    .map((q) => q.id);
}

/** Тело POST /submit (вызывать после проверки анкеты и полноты ответов). */
export function buildSubmitBody(draft, campaign) {
  return {
    submission_key: draft.submissionKey,
    full_name: clean(draft.fullName),
    faculty_code: draft.facultyCode,
    specialty: clean(draft.specialty),
    age: Number(draft.age),
    gender: draft.gender,
    consent_accepted: true,
    consent_version: campaign.consent.version,
    answers: campaign.questions.map((q) => ({
      question_id: q.id,
      option_id: draft.answers[q.id],
    })),
  };
}
