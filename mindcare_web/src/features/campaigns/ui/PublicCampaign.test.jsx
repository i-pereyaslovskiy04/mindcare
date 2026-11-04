import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PublicCampaign from './PublicCampaign';
import { getPublicCampaign, submitPublicCampaign } from '../../../api/campaigns.api';

jest.mock('../../../api/campaigns.api');

const CAMPAIGN = {
  title: '1 курс',
  test_title: 'ИТО',
  instruction: 'Отвечайте искренне.',
  consent: { version: 1, title: 'Согласие', content: 'Текст согласия' },
  faculties: [{ code: 'law', label: 'Юридический факультет' }],
  questions: [
    { id: 10, number: 1, text: 'Первое утверждение', options: [{ id: 101, text: 'Да' }, { id: 102, text: 'Нет' }] },
    { id: 11, number: 2, text: 'Второе утверждение', options: [{ id: 111, text: 'Да' }, { id: 112, text: 'Нет' }] },
  ],
};

const KEY = 'mindcare.campaign.draft.tok';

function prefill(overrides = {}) {
  window.sessionStorage.setItem(KEY, JSON.stringify({
    submissionKey: 'sub-1',
    fullName: 'Иванова Мария',
    facultyCode: 'law',
    specialty: 'Юриспруденция',
    age: '18',
    gender: 'female',
    consentAccepted: true,
    answers: {},
    ...overrides,
  }));
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.scrollTo = jest.fn();
  Element.prototype.scrollIntoView = jest.fn();
  getPublicCampaign.mockReset();
  submitPublicCampaign.mockReset();
  getPublicCampaign.mockResolvedValue(CAMPAIGN);
});

test('недействительная ссылка — понятное сообщение без формы', async () => {
  const err = new Error('nf');
  err.status = 404;
  getPublicCampaign.mockRejectedValue(err);
  render(<PublicCampaign token="tok" />);
  expect(await screen.findByText('Опрос недоступен')).toBeInTheDocument();
  expect(screen.queryByText('Перейти к вопросам')).not.toBeInTheDocument();
});

test('без согласия к вопросам не перейти', async () => {
  prefill({ consentAccepted: false });
  render(<PublicCampaign token="tok" />);
  await userEvent.click(await screen.findByRole('button', { name: 'Перейти к вопросам' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Без согласия');
  expect(screen.queryByText('Первое утверждение')).not.toBeInTheDocument();
});

test('пропущенный вопрос — отправки нет, подсказка', async () => {
  prefill({ answers: { 10: 101 } });
  render(<PublicCampaign token="tok" />);
  await userEvent.click(await screen.findByRole('button', { name: 'Перейти к вопросам' }));
  await userEvent.click(screen.getByRole('button', { name: 'Отправить ответы' }));
  expect(submitPublicCampaign).not.toHaveBeenCalled();
  expect(screen.getByRole('alert')).toHaveTextContent('Осталось ответить на вопросов: 1');
  expect(screen.getByText('Выберите ответ')).toBeInTheDocument();
});

test('полное прохождение — отправка, «Спасибо», черновик удалён', async () => {
  prefill();
  submitPublicCampaign.mockResolvedValue({ status: 'accepted' });
  render(<PublicCampaign token="tok" />);
  await userEvent.click(await screen.findByRole('button', { name: 'Перейти к вопросам' }));
  expect(screen.getByText('Отвечено 0 из 2')).toBeInTheDocument();

  const radios = screen.getAllByRole('radio');
  await userEvent.click(radios[0]);   // 1 — Да
  await userEvent.click(radios[3]);   // 2 — Нет
  expect(screen.getByText('Отвечено 2 из 2')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Отправить ответы' }));

  expect(await screen.findByText('Спасибо за участие!')).toBeInTheDocument();
  expect(submitPublicCampaign).toHaveBeenCalledWith('tok', expect.objectContaining({
    submission_key: 'sub-1',
    full_name: 'Иванова Мария',
    consent_version: 1,
    answers: [{ question_id: 10, option_id: 101 }, { question_id: 11, option_id: 112 }],
  }));
  expect(window.sessionStorage.getItem(KEY)).toBeNull();
});

test.each([
  [422, 'Проверьте анкету и ответы'],
  [503, 'Сервис временно не может сохранить ответы'],
  [500, 'Не удалось отправить ответы'],
])('ошибка %i — своё сообщение, черновик сохранён', async (status, text) => {
  prefill({ answers: { 10: 101, 11: 111 } });
  const err = new Error('x');
  err.status = status;
  submitPublicCampaign.mockRejectedValue(err);
  render(<PublicCampaign token="tok" />);
  await userEvent.click(await screen.findByRole('button', { name: 'Перейти к вопросам' }));
  await userEvent.click(screen.getByRole('button', { name: 'Отправить ответы' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(text);
  expect(JSON.parse(window.sessionStorage.getItem(KEY)).answers).toEqual({ 10: 101, 11: 111 });
});

test('обновилось согласие — возврат к анкете, согласие снято, анкета перезагружена', async () => {
  prefill({ answers: { 10: 101, 11: 111 } });
  const err = new Error('outdated');
  err.status = 409;
  err.code = 'consent_outdated';
  submitPublicCampaign.mockRejectedValue(err);
  render(<PublicCampaign token="tok" />);
  await userEvent.click(await screen.findByRole('button', { name: 'Перейти к вопросам' }));
  await userEvent.click(screen.getByRole('button', { name: 'Отправить ответы' }));
  expect(await screen.findByText(/Текст согласия обновился/)).toBeInTheDocument();
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  await waitFor(() => expect(getPublicCampaign).toHaveBeenCalledTimes(2));
});
