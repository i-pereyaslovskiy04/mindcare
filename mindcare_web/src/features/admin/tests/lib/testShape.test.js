/**
 * testShape — преобразования дерева теста между формой, backend-видом и
 * предпросмотром. Ключевое требование: предпросмотр показывает ровно то, что
 * увидит студент, и адресует ответы так же, как их поймёт preview-score.
 */

import {
  toBackendQuestion, toPreviewQuestions, toPreviewAnswers, isQuestionComplete,
} from './testShape';

const choice = (over = {}) => ({
  _key: 'k1',
  question_text: '  Как часто?  ',
  question_type: 'single_choice',
  is_required: true,
  scale: '',
  config: { min: 0, max: 10, step: 1 },
  options: [
    { _key: 'o1', option_text: ' Никогда ', value_score: 0 },
    { _key: 'o2', option_text: 'Часто', value_score: 3 },
  ],
  ...over,
});

const scaleQ = (over = {}) => ({
  _key: 'k2',
  question_text: 'Оцените',
  question_type: 'scale',
  is_required: true,
  scale: '',
  config: { min: 1, max: 7, step: 2 },
  options: [],
  ...over,
});

// ── isQuestionComplete ────────────────────────────────────────────────────────

test('вопрос без текста не готов к предпросмотру', () => {
  expect(isQuestionComplete(choice({ question_text: '   ' }))).toBe(false);
});

test('choice-вопрос с пустым вариантом не готов', () => {
  expect(isQuestionComplete(choice({
    options: [{ _key: 'a', option_text: 'ok', value_score: 0 },
      { _key: 'b', option_text: '  ', value_score: 1 }],
  }))).toBe(false);
});

test('scale-вопрос готов без вариантов', () => {
  expect(isQuestionComplete(scaleQ())).toBe(true);
});

// ── toPreviewQuestions ────────────────────────────────────────────────────────

test('предпросмотр НЕ содержит value_score — студент ключа теста не видит', () => {
  const [q] = toPreviewQuestions([choice()]);
  q.options.forEach((o) => expect(o).not.toHaveProperty('value_score'));
  expect(JSON.stringify(q)).not.toContain('value_score');
});

test('предпросмотр синтезирует id и обрезает пробелы', () => {
  const [q] = toPreviewQuestions([choice()]);
  expect(q.id).toBe(1);
  expect(q.question_text).toBe('Как часто?');
  expect(q.options.map((o) => o.id)).toEqual([1000, 1001]);
  expect(q.options.map((o) => o.option_text)).toEqual(['Никогда', 'Часто']);
});

test('незаполненные вопросы в предпросмотр не попадают', () => {
  const result = toPreviewQuestions([
    choice(),
    choice({ _key: 'k9', question_text: '' }),
    scaleQ(),
  ]);
  expect(result.map((q) => q.question_text)).toEqual(['Как часто?', 'Оцените']);
  expect(result.map((q) => q.id)).toEqual([1, 2]);   // нумерация без дыр
});

test('scale переносит config, choice — нет', () => {
  const [c, s] = toPreviewQuestions([choice(), scaleQ()]);
  expect(c.config).toEqual({});
  expect(s.config).toEqual({ min: 1, max: 7, step: 2 });
});

// ── toPreviewAnswers ──────────────────────────────────────────────────────────

test('ответы адресуются по order, а не по синтетическому id', () => {
  const questions = toPreviewQuestions([choice(), scaleQ()]);
  const answers = { 1: 1001, 2: 5 };
  expect(toPreviewAnswers(questions, answers)).toEqual([
    { question_order: 0, option_order: 1 },
    { question_order: 1, scale_value: 5 },
  ]);
});

test('multiple_choice отдаёт список option_order', () => {
  const multi = choice({
    question_type: 'multiple_choice',
    options: [
      { _key: 'a', option_text: 'A', value_score: 1 },
      { _key: 'b', option_text: 'B', value_score: 2 },
      { _key: 'c', option_text: 'C', value_score: 3 },
    ],
  });
  const questions = toPreviewQuestions([multi]);
  const answers = { 1: [1000, 1002] };
  expect(toPreviewAnswers(questions, answers)).toEqual([
    { question_order: 0, selected_option_orders: [0, 2] },
  ]);
});

test('неотвеченные и пустые ответы не отправляются', () => {
  const free = choice({ question_type: 'free_text', options: [] });
  const questions = toPreviewQuestions([choice(), free]);
  expect(toPreviewAnswers(questions, {})).toEqual([]);
  expect(toPreviewAnswers(questions, { 2: '   ' })).toEqual([]);
  expect(toPreviewAnswers(questions, { 2: 'тревожно' })).toEqual([
    { question_order: 1, free_text_answer: 'тревожно' },
  ]);
});

test('order предпросмотра совпадает с question_order backend-вида', () => {
  const form = [choice(), choice({ _key: 'kx', question_text: '' }), scaleQ()];
  const complete = form.filter(isQuestionComplete);
  const backend = complete.map(toBackendQuestion);
  const preview = toPreviewQuestions(form);
  expect(backend.map((q) => q.question_order)).toEqual(preview.map((q) => q.id - 1));
});
