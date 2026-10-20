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

test('409 показывает объяснение и предлагает создать копию', async () => {
  const err = new Error('По этому тесту уже есть результаты');
  err.status = 409;
  testsApi.updateTest.mockRejectedValue(err);
  testsApi.duplicateTest.mockResolvedValue({ uuid: 'copy-uuid' });

  renderPage();
  const qText = await screen.findByDisplayValue('Как часто вам было плохо?');
  userEvent.type(qText, '!');
  userEvent.click(screen.getByRole('button', { name: /Сохранить изменения/ }));

  const notice = await screen.findByRole('alert');
  expect(notice).toHaveTextContent(/вопросы изменить нельзя/i);

  userEvent.click(screen.getByRole('button', { name: /Создать копию и править её/ }));
  await waitFor(() => expect(testsApi.duplicateTest).toHaveBeenCalledWith(TEST_UUID));
});

test('после перехода на копию баннер «есть результаты» пропадает', async () => {
  const err = new Error('По этому тесту уже есть результаты');
  err.status = 409;
  testsApi.updateTest.mockRejectedValue(err);
  testsApi.duplicateTest.mockResolvedValue({ uuid: COPY_UUID });

  const { rerender } = renderPage();
  const qText = await screen.findByDisplayValue('Как часто вам было плохо?');
  userEvent.type(qText, '!');
  userEvent.click(screen.getByRole('button', { name: /Сохранить изменения/ }));
  await screen.findByRole('alert');

  // копия — тот же маршрут с другим :uuid, компонент не размонтируется
  testsApi.getAdminTest.mockResolvedValue({ ...loadedTest, uuid: COPY_UUID, is_active: false });
  userEvent.click(screen.getByRole('button', { name: /Создать копию и править её/ }));
  await waitFor(() => expect(mockRoute.uuid).toBe(COPY_UUID));
  rerender(<TestFormPage />);

  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
});
