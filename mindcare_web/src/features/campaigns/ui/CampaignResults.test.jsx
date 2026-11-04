import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CampaignResults from './CampaignResults';
import { getCampaignResults } from '../../../api/campaigns.api';

jest.mock('../../../api/campaigns.api');

const LEVELS = {
  low: 'Гипоэмотивность', norm: 'Норма', accent: 'Акцентуированные черты',
  maladaptive: 'Дезадаптирующие свойства',
};

function payload(overrides = {}) {
  return {
    profile: 'ito_sobchik',
    scales: [{ code: 'L', label: 'L Ложь' }, { code: 'VIII', label: 'VIII Лабильность' }],
    level_labels: LEVELS,
    type_names: ['Неуравновешенный'],
    faculties: [{ code: 'law', label: 'Юридический факультет' }],
    total_all: 2,
    items: [
      {
        uuid: 'r1', full_name: 'Иванов Иван', faculty_code: 'law',
        faculty_label: 'Юридический факультет', specialty: 'x', age: 18,
        gender: 'male', submitted_at: '2026-11-04T10:00:00Z',
        scores: { L: 7, VIII: 9 }, levels: { L: 'invalid', VIII: 'maladaptive' },
        is_valid: false, types: ['Неуравновешенный (недостоверно)'],
      },
    ],
    summary: {
      total: 1, valid: 0, invalid: 1, with_type: 1,
      scales: [
        { scale: 'L', label: 'L Ложь', mean: 7, min: 7, max: 7, levels: { valid: 0, invalid: 1 } },
        { scale: 'VIII', label: 'VIII Лабильность', mean: 8.5, min: 8, max: 9,
          levels: { low: 0, norm: 0, accent: 0, maladaptive: 1 } },
      ],
      types: [{ name: 'Неуравновешенный', count: 1, invalid: 1 }],
      by_faculty: [{ code: 'law', label: 'Юридический факультет', count: 1, valid: 0, with_type: 1, means: {} }],
      by_gender: [{ code: 'male', label: 'Муж', count: 1, valid: 0, with_type: 1, means: {} }],
    },
    ...overrides,
  };
}

beforeEach(() => {
  getCampaignResults.mockReset();
});

test('сводка, распределение уровней и строка участника с уровнем для дикторов', async () => {
  getCampaignResults.mockResolvedValue(payload());
  render(<CampaignResults campaignUuid="c-1" />);
  expect(await screen.findByText('Иванов Иван')).toBeInTheDocument();
  expect(getCampaignResults).toHaveBeenCalledWith('c-1', {
    faculty_code: '', gender: '', validity: '', type: '',
  });
  expect(screen.getByRole('group', { name: 'Недостоверных' })).toHaveTextContent('1');
  expect(screen.getByText('8,5')).toBeInTheDocument();                 // среднее VIII
  expect(screen.getByText('достоверно: 0; недостоверно: 1')).toBeInTheDocument();
  const row = screen.getByRole('row', { name: /Иванов Иван/ });
  expect(within(row).getByText('(Дезадаптирующие свойства)', { exact: false }))
    .toBeInTheDocument();
  expect(within(row).getByText('Неуравновешенный (недостоверно)')).toBeInTheDocument();
});

test('пустая кампания — понятное сообщение', async () => {
  getCampaignResults.mockResolvedValue(payload({ total_all: 0, items: [] }));
  render(<CampaignResults campaignUuid="c-1" />);
  expect(await screen.findByText('Пока никто не прошёл тестирование.')).toBeInTheDocument();
});

test('ошибка — сообщение и повтор', async () => {
  getCampaignResults.mockRejectedValueOnce(new Error('Сбой журнала'));
  getCampaignResults.mockResolvedValueOnce(payload());
  render(<CampaignResults campaignUuid="c-1" />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Сбой журнала');
  await userEvent.click(screen.getByRole('button', { name: 'Повторить' }));
  expect(await screen.findByText('Иванов Иван')).toBeInTheDocument();
});
