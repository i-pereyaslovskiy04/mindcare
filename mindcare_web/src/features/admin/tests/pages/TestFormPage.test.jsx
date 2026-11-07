/**
 * TestFormPage — dirty-tracking вложенных коллекций при редактировании.
 *
 * Вопросы теста, по которому уже есть результаты, менять нельзя (backend → 409:
 * student_answers ссылается на questions/options через ON DELETE RESTRICT).
 * Раньше конструктор всегда клал questions/interpretations в PATCH, поэтому
 * даже переименование такого теста упиралось в ошибку. Проверяем, что
 * неизменённые коллекции в запрос не попадают, а изменённые — попадают.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TestFormPage from './TestFormPage';
import * as testsApi from '../../../../api/tests.api';

const TEST_UUID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
const COPY_UUID = '11111111-2222-3333-4444-555555555555';

// Мутируемый «текущий маршрут»: navigate на копию меняет только :uuid, компонент
// при этом не размонтируется — это и проверяем.
const mockRoute = { uuid: TEST_UUID };
const mockNavigate = jest.fn();

// CRA включает resetMocks:true — реализацию задаём в beforeEach, иначе её стирает
function trackNavigation(to) {
  const m = /\/admin\/tests\/([^/]+)$/.exec(to);
  if (m) mockRoute.uuid = m[1];
}

// react-router-dom v7 не резолвится в jest CRA — мокаем, как в остальных тестах
jest.mock('react-router-dom', () => ({
  useParams: () => ({ uuid: mockRoute.uuid }),
  useNavigate: () => mockNavigate,
}), { virtual: true });

jest.mock('../../../../api/tests.api');
jest.mock('../../../../api/articles.api', () => ({ getAdminCategories: jest.fn(() => Promise.resolve([])) }));
jest.mock('../../../../api/tags.api', () => ({ getTagsPublic: jest.fn(() => Promise.resolve([])) }));

const loadedTest = {
  uuid: TEST_UUID,
  title: 'PHQ-9',
  description: 'Скрининг',
  scoring: 'sum',
  time_limit_min: null,
  is_active: true,
  categories: [],
  tags: [],
  questions: [{
    id: 1,
    question_text: 'Как часто вам было плохо?',
    question_order: 1,
    question_type: 'single_choice',
    is_required: true,
    config: {},
    options: [
      { id: 10, option_text: 'Никогда', option_order: 0, value_score: 0 },
      { id: 11, option_text: 'Часто', option_order: 1, value_score: 3 },
    ],
  }],
  interpretations: [{
    id: 5, scale_name: null, min_score: 0, max_score: 3,
    label: 'Низкий', recommendation: 'ok',
  }],
};

function renderPage() {
  return render(<TestFormPage />);
}

beforeEach(() => {
  jest.clearAllMocks();
  mockRoute.uuid = TEST_UUID;
  mockNavigate.mockImplementation(trackNavigation);
  testsApi.getAdminTest.mockResolvedValue(loadedTest);
  testsApi.updateTest.mockResolvedValue({ uuid: TEST_UUID });
  // дебаунс-анализ порогов уходит через 600 мс после загрузки формы
  testsApi.analyzeTest.mockResolvedValue({ score_bounds: [], issues: [] });
});

test('переименование не отправляет неизменённые questions и interpretations', async () => {
  renderPage();

  const titleInput = await screen.findByDisplayValue('PHQ-9');
  userEvent.clear(titleInput);
  userEvent.type(titleInput, 'PHQ-9 (2026)');
  userEvent.click(screen.getByRole('button', { name: /Сохранить изменения/ }));

  await waitFor(() => expect(testsApi.updateTest).toHaveBeenCalled());
  const [, payload] = testsApi.updateTest.mock.calls[0];
  expect(payload.title).toBe('PHQ-9 (2026)');
  expect(payload).not.toHaveProperty('questions');
  expect(payload).not.toHaveProperty('interpretations');
});

test('изменение текста вопроса отправляет questions', async () => {
  renderPage();

  const qText = await screen.findByDisplayValue('Как часто вам было плохо?');
  userEvent.type(qText, ' (уточнено)');
  userEvent.click(screen.getByRole('button', { name: /Сохранить изменения/ }));

  await waitFor(() => expect(testsApi.updateTest).toHaveBeenCalled());
  const [, payload] = testsApi.updateTest.mock.calls[0];
  expect(payload.questions).toHaveLength(1);
  expect(payload.questions[0].question_text).toContain('(уточнено)');
});

test('409 объясняет запрет и предлагает новую версию (ADR-037)', async () => {
  const err = new Error('По этому тесту уже есть результаты');
  err.status = 409;
  testsApi.updateTest.mockRejectedValue(err);
  testsApi.createNewVersion.mockResolvedValue({ uuid: COPY_UUID });

  renderPage();
  const qText = await screen.findByDisplayValue('Как часто вам было плохо?');
  userEvent.type(qText, '!');
  userEvent.click(screen.getByRole('button', { name: /Сохранить изменения/ }));

  const notice = await screen.findByRole('alert');
  expect(notice).toHaveTextContent(/Вопросы, баллы и правила обработки этой версии не меняются/);

  userEvent.click(screen.getByRole('button', { name: 'Создать новую версию' }));
  await waitFor(() => expect(testsApi.createNewVersion).toHaveBeenCalledWith(TEST_UUID));
  await waitFor(() => expect(mockRoute.uuid).toBe(COPY_UUID));
});

test('после перехода на новую версию баннер «есть результаты» пропадает', async () => {
  const err = new Error('По этому тесту уже есть результаты');
  err.status = 409;
  testsApi.updateTest.mockRejectedValue(err);
  testsApi.createNewVersion.mockResolvedValue({ uuid: COPY_UUID });

  const { rerender } = renderPage();
  const qText = await screen.findByDisplayValue('Как часто вам было плохо?');
  userEvent.type(qText, '!');
  userEvent.click(screen.getByRole('button', { name: /Сохранить изменения/ }));
  await screen.findByRole('alert');

  // версия — тот же маршрут с другим :uuid, компонент не размонтируется
  testsApi.getAdminTest.mockResolvedValue({ ...loadedTest, uuid: COPY_UUID, version: 2, status: 'draft' });
  userEvent.click(screen.getByRole('button', { name: 'Создать новую версию' }));
  await waitFor(() => expect(mockRoute.uuid).toBe(COPY_UUID));
  rerender(<TestFormPage />);

  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  expect(await screen.findByText('Версия 2')).toBeInTheDocument();
});

test('«Сохранить только тексты» шлёт тексты по исходным номерам', async () => {
  const err = new Error('По этому тесту уже есть результаты');
  err.status = 409;
  testsApi.updateTest.mockRejectedValue(err);
  testsApi.correctTexts.mockResolvedValue({ uuid: TEST_UUID });
  testsApi.getAdminTest.mockResolvedValue({ ...loadedTest, updated_at: '2026-11-06T10:00:00Z' });

  renderPage();
  const qText = await screen.findByDisplayValue('Как часто вам было плохо?');
  userEvent.type(qText, ' (уточнено)');
  userEvent.click(screen.getByRole('button', { name: /Сохранить изменения/ }));
  await screen.findByRole('alert');
  userEvent.click(screen.getByRole('button', { name: 'Сохранить только тексты' }));

  await waitFor(() => expect(testsApi.correctTexts).toHaveBeenCalled());
  const [uuidArg, body] = testsApi.correctTexts.mock.calls[0];
  expect(uuidArg).toBe(TEST_UUID);
  expect(body).toEqual({
    expected_updated_at: '2026-11-06T10:00:00Z',
    questions: [{
      question_order: 1,
      question_text: 'Как часто вам было плохо? (уточнено)',
      options: [{ option_order: 0, option_text: 'Никогда' }, { option_order: 1, option_text: 'Часто' }],
    }],
  });
});

test('опубликованная методика — кнопка «Новая версия»; заменённая — пометка', async () => {
  testsApi.getAdminTest.mockResolvedValue({ ...loadedTest, status: 'published', version: 3 });
  const { unmount } = renderPage();
  expect(await screen.findByRole('button', { name: 'Новая версия' })).toBeInTheDocument();
  expect(screen.getByText('Версия 3')).toBeInTheDocument();
  unmount();

  testsApi.getAdminTest.mockResolvedValue({
    ...loadedTest, status: 'published', superseded_at: '2026-11-06T10:00:00Z',
  });
  renderPage();
  expect(await screen.findByText(/Заменена новой версией/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Новая версия' })).toBeNull();
});

// ── ADR-037: правила обработки и «только по ссылке» ──────────────────────────

const RULES = {
  version: 1, instruction: null,
  scales: [{ code: 'A', label: 'Тревога', main: true }],
  levels: [{ code: 'low', label: 'Низкий', min: 0, max: 3 }],
  validity: null, types: null,
};

test('неизменённые правила не отправляются, campaign_only — отправляется', async () => {
  testsApi.getAdminTest.mockResolvedValue({ ...loadedTest, scoring_rules: RULES, campaign_only: true });
  renderPage();
  const titleInput = await screen.findByDisplayValue('PHQ-9');
  expect(screen.getByDisplayValue('Тревога')).toBeInTheDocument();
  userEvent.type(titleInput, '!');
  userEvent.click(screen.getByRole('button', { name: /Сохранить изменения/ }));
  await waitFor(() => expect(testsApi.updateTest).toHaveBeenCalled());
  const [, payload] = testsApi.updateTest.mock.calls[0];
  expect(payload).not.toHaveProperty('scoring_rules');
  expect(payload.campaign_only).toBe(true);
});

test('изменённая подпись шкалы уходит в scoring_rules', async () => {
  testsApi.getAdminTest.mockResolvedValue({ ...loadedTest, scoring_rules: RULES });
  renderPage();
  const label = await screen.findByDisplayValue('Тревога');
  userEvent.type(label, ' (Т)');
  userEvent.click(screen.getByRole('button', { name: /Сохранить изменения/ }));
  await waitFor(() => expect(testsApi.updateTest).toHaveBeenCalled());
  const [, payload] = testsApi.updateTest.mock.calls[0];
  expect(payload.scoring_rules.scales[0].label).toBe('Тревога (Т)');
});

test('снятие галочки правил отправляет scoring_rules: null', async () => {
  testsApi.getAdminTest.mockResolvedValue({ ...loadedTest, scoring_rules: RULES });
  renderPage();
  await screen.findByDisplayValue('Тревога');
  userEvent.click(screen.getByRole('checkbox', { name: /Задать правила обработки/ }));
  userEvent.click(screen.getByRole('button', { name: /Сохранить изменения/ }));
  await waitFor(() => expect(testsApi.updateTest).toHaveBeenCalled());
  const [, payload] = testsApi.updateTest.mock.calls[0];
  expect(payload.scoring_rules).toBeNull();
});


test('есть ответы — подсказка с вариантами видна сразу при открытии', async () => {
  testsApi.getAdminTest.mockResolvedValue({
    ...loadedTest, status: 'published', has_results: true, campaigns_count: 2,
  });
  renderPage();
  const note = await screen.findByRole('note');
  expect(note).toHaveTextContent('По этой методике уже есть ответы · используется в кампаниях: 2');
  expect(note).toHaveTextContent(/Исправить опечатку/);
  expect(screen.getByRole('button', { name: 'Создать новую версию' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Сохранить только тексты' })).toBeInTheDocument();
});

test('в кампаниях без ответов — предупреждение, что правки применятся к ним', async () => {
  testsApi.getAdminTest.mockResolvedValue({ ...loadedTest, has_results: false, campaigns_count: 1 });
  renderPage();
  expect(await screen.findByRole('note')).toHaveTextContent(/правки сразу применятся и к этим кампаниям/);
});
