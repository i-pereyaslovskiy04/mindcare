/**
 * TestPreviewModal — предпросмотр методики глазами студента и пробный подсчёт.
 *
 * Проверяем главное: рендерится тем же контролом, что видит студент; баллы
 * вариантов не показываются; подсчёт уходит на бэкенд с адресацией по order
 * и ничего не сохраняет.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TestPreviewModal from './TestPreviewModal';
import * as testsApi from '../../../../api/tests.api';

jest.mock('../../../../api/tests.api');

const questions = [
  {
    _key: 'k1',
    question_text: 'Как часто вам было плохо?',
    question_type: 'single_choice',
    is_required: true,
    scale: '',
    config: { min: 0, max: 10, step: 1 },
    options: [
      { _key: 'o1', option_text: 'Никогда', value_score: 0 },
      { _key: 'o2', option_text: 'Часто', value_score: 3 },
    ],
  },
];

const interpretations = [{
  _key: 'i1', scale_name: '', min_score: 0, max_score: 3,
  label: 'Низкий', recommendation: 'всё в порядке',
}];

function renderModal(over = {}) {
  return render(
    <TestPreviewModal
      title="PHQ-9"
      description="Скрининг"
      scoring="sum"
      questions={questions}
      interpretations={interpretations}
      onClose={jest.fn()}
      {...over}
    />,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  testsApi.previewScore.mockResolvedValue({
    total_score: 3, max_possible: 3, scoring_used: 'sum',
    recommendations: 'Низкий: всё в порядке', scales: [],
  });
});

test('показывает вопрос и варианты, но не баллы вариантов', () => {
  renderModal();
  expect(screen.getByText(/Как часто вам было плохо\?/)).toBeInTheDocument();
  expect(screen.getByLabelText('Никогда')).toBeInTheDocument();
  expect(screen.getByLabelText('Часто')).toBeInTheDocument();
  // «3» — балл варианта: в предпросмотре его быть не должно
  expect(screen.queryByDisplayValue('3')).not.toBeInTheDocument();
});

test('подсчёт уходит на бэкенд с адресацией по order', async () => {
  renderModal();
  userEvent.click(screen.getByLabelText('Часто'));
  userEvent.click(screen.getByRole('button', { name: /Посчитать результат/ }));

  await waitFor(() => expect(testsApi.previewScore).toHaveBeenCalled());
  const [payload] = testsApi.previewScore.mock.calls[0];
  expect(payload.scoring).toBe('sum');
  expect(payload.answers).toEqual([{ question_order: 0, option_order: 1 }]);
  expect(payload.questions[0].options[1].value_score).toBe(3);   // ключ уходит на бэк, не в UI
});

test('результат показывается с расшифровкой', async () => {
  renderModal();
  userEvent.click(screen.getByLabelText('Часто'));
  userEvent.click(screen.getByRole('button', { name: /Посчитать результат/ }));

  expect(await screen.findByText(/Низкий: всё в порядке/)).toBeInTheDocument();
  expect(screen.getByText(/из 3/)).toBeInTheDocument();
});

test('балл без подходящего порога помечается предупреждением', async () => {
  testsApi.previewScore.mockResolvedValue({
    total_score: 5, max_possible: 6, scoring_used: 'sum',
    recommendations: null, scales: [],
  });
  renderModal();
  userEvent.click(screen.getByRole('button', { name: /Посчитать результат/ }));

  expect(await screen.findByText(/нет подходящего порога/)).toBeInTheDocument();
});

test('пустое дерево показывает подсказку вместо вопросов', () => {
  renderModal({ questions: [] });
  expect(screen.getByText(/Пока нечего показать/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Посчитать результат/ })).not.toBeInTheDocument();
});

test('сообщает, что ничего не сохраняется', () => {
  renderModal();
  expect(screen.getByText(/никуда не сохраняются/)).toBeInTheDocument();
});
