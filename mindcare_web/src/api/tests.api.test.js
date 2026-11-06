import {
  analyzeMyTest, analyzeTest, correctMyTexts, correctTexts, createMyNewVersion,
  createNewVersion, previewMyScore, previewScore,
} from './tests.api';
import { apiFetch } from './client';

jest.mock('./client');

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({});
});

const RULES = { version: 1, scales: [{ code: 'A', label: 'A' }] };

test.each([
  [analyzeTest, '/api/admin/tests/analyze'],
  [analyzeMyTest, '/api/psychologist/tests/analyze'],
])('анализ передаёт правила обработки (ADR-037) — %#', (fn, url) => {
  fn({ scoring: 'sum', questions: [], interpretations: [], scoring_rules: RULES });
  expect(apiFetch).toHaveBeenCalledWith(url, expect.objectContaining({ method: 'POST' }));
  expect(JSON.parse(apiFetch.mock.calls[0][1].body).scoring_rules).toEqual(RULES);
});

test.each([
  [previewScore, '/api/admin/tests/preview-score'],
  [previewMyScore, '/api/psychologist/tests/preview-score'],
])('предпросмотр передаёт правила и ответы — %#', (fn, url) => {
  fn({ scoring: 'sum', questions: [], interpretations: [], answers: [{ question_order: 0 }],
    scoring_rules: RULES });
  const body = JSON.parse(apiFetch.mock.calls[0][1].body);
  expect(apiFetch.mock.calls[0][0]).toBe(url);
  expect(body.scoring_rules).toEqual(RULES);
  expect(body.answers).toHaveLength(1);
});

test('без правил — null', () => {
  analyzeTest({ scoring: 'sum', questions: [], interpretations: [] });
  expect(JSON.parse(apiFetch.mock.calls[0][1].body).scoring_rules).toBeNull();
});

test('новая версия и исправление текстов', () => {
  createNewVersion('u');
  expect(apiFetch).toHaveBeenLastCalledWith('/api/admin/tests/u/new-version', { method: 'POST' });
  createMyNewVersion('u');
  expect(apiFetch).toHaveBeenLastCalledWith('/api/psychologist/tests/u/new-version', { method: 'POST' });
  correctTexts('u', { questions: [] });
  expect(apiFetch).toHaveBeenLastCalledWith('/api/admin/tests/u/texts',
    { method: 'PATCH', body: JSON.stringify({ questions: [] }) });
  correctMyTexts('u', { questions: [] });
  expect(apiFetch).toHaveBeenLastCalledWith('/api/psychologist/tests/u/texts',
    { method: 'PATCH', body: JSON.stringify({ questions: [] }) });
});
