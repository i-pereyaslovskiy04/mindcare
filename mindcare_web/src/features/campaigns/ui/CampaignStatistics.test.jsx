import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CampaignResults from './CampaignResults';
import { getCampaignResults, getCampaignStatistics } from '../../../api/campaigns.api';

jest.mock('../../../api/campaigns.api');

const RESULTS = {
  has_rules: false, has_validity: false, validity_title: 'Недостоверных', type_threshold: null,
  levels: [], level_labels: {}, scale_levels: {}, scales: [{ code: 'A', label: 'Тревога' }],
  type_names: [], faculties: [], total_all: 6, items: [],
  summary: { total: 6, valid: null, invalid: null, with_type: 0,
    scales: [{ scale: 'A', label: 'Тревога', mean: 4, min: 2, max: 7, levels: {} }],
    types: [], by_faculty: [], by_gender: [] },
};

const STATS = {
  total: 6, min_group: 5, too_few: false,
  by_day: [{ date: '2026-11-07', count: 6 }],
  scales: [{ scale: 'A', label: 'Тревога', bins: [{ score: 2, count: 1 }, { score: 3, count: 5 }] }],
  questions: [
    { number: 1, text: 'Первый вопрос', answered: 6,
      options: [{ text: 'Да', count: 4, percent: 66.7 }, { text: 'Нет', count: 2, percent: 33.3 }] },
    { number: 2, text: 'Второй вопрос', answered: 6,
      options: [{ text: 'Да', count: 6, percent: 100 }, { text: 'Нет', count: 0, percent: 0 }] },
  ],
};

beforeEach(() => {
  getCampaignResults.mockReset().mockResolvedValue(RESULTS);
  getCampaignStatistics.mockReset();
});

test('вкладка «Статистика»: загрузка по требованию, ответы, поиск вопроса', async () => {
  getCampaignStatistics.mockResolvedValue(STATS);
  render(<CampaignResults campaignUuid="c-1" />);
  await userEvent.click(await screen.findByRole('tab', { name: 'Статистика' }));
  expect(getCampaignStatistics).toHaveBeenCalledWith('c-1', {
    faculty_code: '', gender: '', validity: '', type: '',
  });
  expect(await screen.findByText('Первый вопрос')).toBeInTheDocument();
  const row = screen.getByRole('row', { name: /Да.*4.*66,7%/ });
  expect(within(row).getByText('66,7%')).toBeInTheDocument();
  expect(screen.getByRole('img', { name: /Тревога: 2 баллов — 1; 3 баллов — 5/ })).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText(/Найти вопрос/), 'второй');
  expect(screen.queryByText('Первый вопрос')).not.toBeInTheDocument();
  expect(screen.getByText('Второй вопрос')).toBeInTheDocument();
});

test('мало участников — пояснение вместо распределений', async () => {
  getCampaignStatistics.mockResolvedValue({ ...STATS, total: 3, too_few: true, questions: [], scales: [] });
  render(<CampaignResults campaignUuid="c-1" />);
  await userEvent.click(await screen.findByRole('tab', { name: 'Статистика' }));
  expect(await screen.findByText(/показываются от 5 человек/)).toBeInTheDocument();
  expect(screen.queryByText('Ответы по вопросам')).not.toBeInTheDocument();
});
