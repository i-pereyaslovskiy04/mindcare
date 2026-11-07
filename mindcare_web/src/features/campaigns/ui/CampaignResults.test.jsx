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
    has_rules: true,
    has_validity: true,
    validity_title: 'Недостоверных (L или F > 5)',
    type_threshold: 8,
    levels: [
      { code: 'low', label: LEVELS.low, min: 0, max: 2, tone: 'low' },
      { code: 'norm', label: LEVELS.norm, min: 3, max: 4, tone: 'norm' },
      { code: 'accent', label: LEVELS.accent, min: 5, max: 7, tone: 'accent' },
      { code: 'maladaptive', label: LEVELS.maladaptive, min: 8, max: 9, tone: 'maladaptive' },
    ],
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

test('пол и факультеты — отдельные таблицы', async () => {
  getCampaignResults.mockResolvedValue(payload());
  render(<CampaignResults campaignUuid="c-1" />);
  const gender = await screen.findByRole('region', { name: 'По полу' });
  expect(within(gender).getByRole('rowheader', { name: 'Муж' })).toBeInTheDocument();
  expect(within(gender).queryByText('Юридический факультет')).toBeNull();
  const faculty = screen.getByRole('region', { name: 'По факультетам' });
  expect(within(faculty).getByRole('rowheader', { name: 'Юридический факультет' }))
    .toBeInTheDocument();
});

test('методика без правил: нет достоверности, типов и уровней', async () => {
  getCampaignResults.mockResolvedValue(payload({
    has_rules: false, has_validity: false, validity_title: 'Недостоверных',
    type_threshold: null, levels: [], level_labels: {}, type_names: [],
    scales: [{ code: 'A', label: 'A' }],
    items: [{
      uuid: 'r1', full_name: 'Петров Пётр', faculty_code: 'law',
      faculty_label: 'Юридический факультет', specialty: 'x', age: 19,
      gender: 'male', submitted_at: '2026-11-04T10:00:00Z',
      scores: { A: 5 }, levels: {}, is_valid: null, types: [],
    }],
    summary: {
      total: 1, valid: null, invalid: null, with_type: 0,
      scales: [{ scale: 'A', label: 'A', mean: 5, min: 5, max: 5, levels: {} }],
      types: [], by_faculty: [], by_gender: [],
    },
  }));
  render(<CampaignResults campaignUuid="c-1" />);
  expect(await screen.findByText('Петров Пётр')).toBeInTheDocument();
  expect(screen.queryByRole('group', { name: 'Недостоверных' })).not.toBeInTheDocument();
  expect(screen.queryByText(/Типы \(все шкалы/)).not.toBeInTheDocument();
  expect(screen.queryByRole('columnheader', { name: 'Достоверность' })).not.toBeInTheDocument();
  expect(screen.queryByText('Цвет балла:', { exact: false })).not.toBeInTheDocument();
});

test('свои уровни шкалы: подписи в сводке, легенде и строке участника', async () => {
  const own = [
    { code: 'norm', label: 'Норма A', min: 0, max: 7, tone: 'low' },
    { code: 'sub', label: 'Субклиническая', min: 8, max: 10, tone: 'norm' },
    { code: 'clin', label: 'Клиническая', min: 11, max: 21, tone: 'maladaptive' },
  ];
  const base = payload();
  getCampaignResults.mockResolvedValue(payload({
    scale_levels: { VIII: own },
    items: [{ ...base.items[0], scores: { L: 7, VIII: 12 }, levels: { L: 'invalid', VIII: 'clin' } }],
    summary: {
      ...base.summary,
      scales: [base.summary.scales[0],
        { ...base.summary.scales[1], levels: { norm: 0, sub: 0, clin: 1 } }],
    },
  }));
  render(<CampaignResults campaignUuid="c-1" />);
  expect(await screen.findByText('Норма A: 0; Субклиническая: 0; Клиническая: 1')).toBeInTheDocument();
  expect(screen.getByText('VIII: Клиническая')).toBeInTheDocument();
  const row = screen.getByRole('row', { name: /Иванов Иван/ });
  expect(within(row).getByText('(Клиническая)', { exact: false })).toBeInTheDocument();
});
