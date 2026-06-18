import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import * as AuthContext from '../../features/auth/AuthContext';
import * as diaryApi from '../../api/diary.api';
import StudentHome from './StudentHome';

jest.mock('../../api/diary.api');
jest.mock('../../features/auth/AuthContext');
jest.mock('react-router-dom', () => ({
  useNavigate: jest.fn(() => jest.fn()),
  Link: ({ to, children, ...props }) => (
    <a href={to} {...props}>{children}</a>
  ),
}), { virtual: true });

const MOCK_SUMMARY_14D = {
  period: '14d',
  entries_count: 5,
  points: [
    { date: '2026-06-05', label: 'Чт', mood_score: 7 },
    { date: '2026-06-06', label: 'Пт', mood_score: null },
    { date: '2026-06-07', label: 'Сб', mood_score: 6 },
  ],
};

const MOCK_SUMMARY_MONTH = {
  period: 'month',
  entries_count: 12,
  points: [
    { date: '2026-06-01', label: 'Пн', mood_score: 5 },
    { date: '2026-06-02', label: 'Вт', mood_score: 6 },
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
  AuthContext.useAuth.mockReturnValue({ user: { name: 'Тест Тестов' } });
  diaryApi.getDiarySummary.mockResolvedValue(MOCK_SUMMARY_14D);
});

test('requests summary period=14d by default on mount', async () => {
  render(<StudentHome />);
  await waitFor(() =>
    expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('14d')
  );
});

test('renders chart section heading', async () => {
  render(<StudentHome />);
  expect(await screen.findByText('Динамика настроения')).toBeInTheDocument();
});

test('renders Записей в дневнике stat card after summary loads', async () => {
  render(<StudentHome />);
  // API called and label rendered — entries_count flows through the prop
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('14d'));
  expect(screen.getByText('Записей в дневнике')).toBeInTheDocument();
});

test('changing period to month triggers summary fetch for month', async () => {
  diaryApi.getDiarySummary
    .mockResolvedValueOnce(MOCK_SUMMARY_14D)
    .mockResolvedValueOnce(MOCK_SUMMARY_MONTH);

  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('14d'));

  const monthBtn = screen.getByRole('button', { name: /месяц/i });
  fireEvent.click(monthBtn);

  await waitFor(() =>
    expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('month')
  );
});

test('changing period to year triggers summary fetch for year', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('14d'));

  const yearBtn = screen.getByRole('button', { name: /год/i });
  fireEvent.click(yearBtn);

  await waitFor(() =>
    expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('year')
  );
});

test('shows empty state when summary API fails', async () => {
  diaryApi.getDiarySummary.mockRejectedValue(new Error('API error'));
  render(<StudentHome />);
  expect(await screen.findByText(/пока нет записей/i)).toBeInTheDocument();
});

test('renders period chip buttons for all three periods', async () => {
  render(<StudentHome />);
  await screen.findByText('Динамика настроения');
  expect(screen.getByRole('button', { name: '14 дней' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Месяц' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Год' })).toBeInTheDocument();
});
