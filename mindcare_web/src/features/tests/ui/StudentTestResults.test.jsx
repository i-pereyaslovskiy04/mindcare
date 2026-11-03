import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import StudentTestResults from './StudentTestResults';
import {
  getStaffTestResult, getStaffTestResultAnswers, getStudentTestResults,
} from '../../../api/tests.api';

jest.mock('../../../api/tests.api');

const apiError = (status) => Object.assign(new Error('x'), { status });
const row = (n) => ({ uuid: `r-${n}`, test_title: `Тест ${n}`, submitted_at: '2026-10-01T10:00:00Z' });

const DETAIL = {
  uuid: 'r-1', test_title: 'Тест 1', total_score: 7, max_possible: 10,
  scoring_used: 'sum', recommendations: 'Исходная рекомендация', submitted_at: '2026-10-01T10:00:00Z',
  scales: [],
};

const ANSWERS = {
  result_uuid: 'r-1', test_title: 'Тест 1', submitted_at: '2026-10-01T10:00:00Z', order: 'test_order',
  items: [
    {
      position: 1, question_text: 'Как вы спите?', question_type: 'single_choice', answered: true,
      media: [{ uuid: 'm1', url: '/media/q.png', kind: 'image', caption: 'Картинка вопроса' }],
      options: [{ option_text: 'Хорошо', media: [{ uuid: 'm2', url: '/media/o.png', kind: 'image', caption: null }] }],
      scale_value: null, scale_min: null, scale_max: null, free_text: null,
    },
    {
      position: 2, question_text: 'Аудио-вопрос', question_type: 'scale', answered: true,
      media: [{ uuid: 'm3', url: '/media/q.mp3', kind: 'audio', caption: null }],
      options: [], scale_value: 4, scale_min: 1, scale_max: 5, free_text: null,
    },
    {
      position: 3, question_text: 'Опишите неделю', question_type: 'free_text', answered: true,
      media: [{ uuid: 'm4', url: '/media/q.mp4', kind: 'video', caption: 'Видео' }],
      options: [], scale_value: null, scale_min: null, scale_max: null, free_text: 'Тяжёлая неделя',
    },
    {
      position: 4, question_text: 'Необязательный', question_type: 'single_choice', answered: false,
      media: [], options: [], scale_value: null, scale_min: null, scale_max: null, free_text: null,
    },
  ],
};

beforeEach(() => jest.resetAllMocks());

async function openFirst() {
  getStudentTestResults.mockResolvedValueOnce({ items: [row(1)], total: 1 });
  getStaffTestResult.mockResolvedValueOnce(DETAIL);
  render(<StudentTestResults studentUuid="c-1" activeRole="psychologist" canViewAnswers />);
  userEvent.click(await screen.findByRole('button', { name: /Тест 1/ }));
  await screen.findByText('Исходная рекомендация');
}

test('ответы: выбранный вариант с текстом и медиа, шкала, свободный текст, «Нет ответа»', async () => {
  await openFirst();
  getStaffTestResultAnswers.mockResolvedValueOnce(ANSWERS);
  userEvent.click(screen.getByRole('button', { name: 'Показать ответы' }));

  expect(await screen.findByText('Хорошо')).toBeInTheDocument();          // option_text выбранного
  expect(screen.queryByText('Плохо')).toBeNull();                         // невыбранного нет
  expect(screen.getByAltText('Картинка вопроса')).toHaveAttribute('src', '/media/q.png');
  const decorative = screen.getByRole('presentation', { hidden: true });   // alt="" варианта
  expect(decorative).toHaveAttribute('src', '/media/o.png');
  expect(decorative).toHaveAttribute('aria-hidden', 'true');
  expect(screen.getByLabelText('Аудио-вопрос')).toHaveAttribute('src', '/media/q.mp3');
  expect(screen.getByLabelText('Видео')).toHaveAttribute('src', '/media/q.mp4');
  expect(screen.getByText(/Значение: 4/)).toHaveTextContent('Значение: 4 (шкала 1–5)');
  expect(screen.getByText('Тяжёлая неделя')).toBeInTheDocument();
  expect(screen.getByText('Нет ответа')).toBeInTheDocument();
  expect(screen.getByText(/порядок показа клиенту не сохраняется/)).toBeInTheDocument();
  expect(getStaffTestResultAnswers).toHaveBeenCalledWith('r-1', 'psychologist');
});

test('без canViewAnswers кнопки ответов нет (модалка супервизора)', async () => {
  getStudentTestResults.mockResolvedValueOnce({ items: [row(1)], total: 1 });
  getStaffTestResult.mockResolvedValueOnce(DETAIL);
  render(<StudentTestResults studentUuid="c-1" activeRole="supervisor" />);
  userEvent.click(await screen.findByRole('button', { name: /Тест 1/ }));
  await screen.findByText('Исходная рекомендация');
  expect(screen.queryByRole('button', { name: 'Показать ответы' })).toBeNull();
});

test('«Показать ещё» догружает следующую страницу', async () => {
  const first = Array.from({ length: 20 }, (_, i) => row(i + 1));
  getStudentTestResults
    .mockResolvedValueOnce({ items: first, total: 21 })
    .mockResolvedValueOnce({ items: [row(21)], total: 21 });
  render(<StudentTestResults studentUuid="c-1" activeRole="psychologist" />);
  await screen.findByRole('button', { name: /Тест 20/ });
  userEvent.click(screen.getByRole('button', { name: 'Показать ещё' }));
  expect(await screen.findByRole('button', { name: /Тест 21/ })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Показать ещё' })).toBeNull();
});

test('404 ответов: ранее загруженное содержимое исчезает с экрана', async () => {
  await openFirst();
  getStaffTestResultAnswers.mockRejectedValueOnce(apiError(404));
  userEvent.click(screen.getByRole('button', { name: 'Показать ответы' }));

  expect(await screen.findByText('Результаты клиента недоступны.')).toBeInTheDocument();
  expect(screen.queryByText('Исходная рекомендация')).toBeNull();
  expect(screen.queryByRole('button', { name: /Тест 1/ })).toBeNull();
});

test('503 ответов: ответы не показаны, сообщение о журнале, результат остаётся', async () => {
  await openFirst();
  getStaffTestResultAnswers.mockRejectedValueOnce(apiError(503));
  userEvent.click(screen.getByRole('button', { name: 'Показать ответы' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/журнале/));
  expect(screen.queryByText('Хорошо')).toBeNull();
  expect(screen.getByText('Исходная рекомендация')).toBeInTheDocument();
});
