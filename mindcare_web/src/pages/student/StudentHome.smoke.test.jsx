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

// Fixed 14-slot frame: all null except last entry (new contract)
const MOCK_SUMMARY_14D = {
  period: '14d',
  entries_count: 3,
  points: [
    ...Array.from({ length: 11 }, (_, i) => ({
      date: `2026-06-${String(i + 5).padStart(2, '0')}`,
      label: 'Пн',
      mood_score: null,
    })),
    { date: '2026-06-16', label: 'Чт', mood_score: 7 },
    { date: '2026-06-17', label: 'Пт', mood_score: null },
    { date: '2026-06-18', label: 'Сб', mood_score: 6 },
    // Note: real API always returns 14 points; smoke mock simplified to 14
  ].slice(0, 14),
};

// Month period: from 1st of month to today (new contract)
const MOCK_SUMMARY_MONTH = {
  period: 'month',
  entries_count: 3,
  points: Array.from({ length: 19 }, (_, i) => ({
    date: `2026-06-${String(i + 1).padStart(2, '0')}`,
    label: i + 1 === 19 ? 'Сегодня' : String(i + 1),
    mood_score: i === 5 ? 5 : i === 10 ? 6 : i === 18 ? 7 : null,
  })),
};

// Year period: all 12 months Jan–Dec; future months have null (new contract)
const MOCK_SUMMARY_YEAR = {
  period: 'year',
  entries_count: 3,
  points: [
    { date: '2026-01-01', label: 'Янв', mood_score: null },
    { date: '2026-02-01', label: 'Фев', mood_score: null },
    { date: '2026-03-01', label: 'Мар', mood_score: 7 },
    { date: '2026-04-01', label: 'Апр', mood_score: null },
    { date: '2026-05-01', label: 'Май', mood_score: 6.5 },
    { date: '2026-06-01', label: 'Июн', mood_score: 8 },
    { date: '2026-07-01', label: 'Июл', mood_score: null },
    { date: '2026-08-01', label: 'Авг', mood_score: null },
    { date: '2026-09-01', label: 'Сен', mood_score: null },
    { date: '2026-10-01', label: 'Окт', mood_score: null },
    { date: '2026-11-01', label: 'Ноя', mood_score: null },
    { date: '2026-12-01', label: 'Дек', mood_score: null },
  ],
};

const MOCK_TODAY_NO_ENTRY   = { entry_date: '2026-06-23', mood_score: null, entry_text: '', emotions: [] };
const MOCK_TODAY_WITH_ENTRY = { entry_date: '2026-06-23', mood_score: 7,    entry_text: 'Хорошо', emotions: ['calm'] };

beforeEach(() => {
  jest.clearAllMocks();
  AuthContext.useAuth.mockReturnValue({ user: { name: 'Тест Тестов' } });
  diaryApi.getDiarySummary.mockResolvedValue(MOCK_SUMMARY_14D);
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_NO_ENTRY);
});

// ─── existing diary summary / chart tests ────────────────────────────────────

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

test('year period renders monthly labels — not 365 daily labels', async () => {
  diaryApi.getDiarySummary
    .mockResolvedValueOnce(MOCK_SUMMARY_14D)
    .mockResolvedValueOnce(MOCK_SUMMARY_YEAR);

  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('14d'));

  const yearBtn = screen.getByRole('button', { name: /год/i });
  fireEvent.click(yearBtn);

  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('year'));
  // Monthly labels from MOCK_SUMMARY_YEAR — all 12 months including future
  expect(await screen.findByText('Мар')).toBeInTheDocument();
  expect(screen.getByText('Июн')).toBeInTheDocument();
  expect(screen.getByText('Дек')).toBeInTheDocument();  // future month visible
});

test('sparse summary (2 real points) shows sparse hint — not empty state', async () => {
  const sparseSummary = {
    period: '14d',
    entries_count: 2,
    points: Array.from({ length: 14 }, (_, i) => ({
      date: `2026-06-${String(i + 6).padStart(2, '0')}`,
      label: i === 13 ? 'Сегодня' : 'Пн',
      mood_score: i === 12 ? 6 : i === 13 ? 7 : null,
    })),
  };
  diaryApi.getDiarySummary.mockResolvedValue(sparseSummary);
  render(<StudentHome />);
  await screen.findByText('Динамика настроения');
  expect(await screen.findByText('Мало данных для тренда')).toBeInTheDocument();
  expect(screen.queryByText(/пока нет записей/i)).not.toBeInTheDocument();
});

test('shows empty state when all period points have null mood_score (no data)', async () => {
  // Backend returns full 14-slot frame with all null — frontend shows empty state
  const allNullSummary = {
    period: '14d',
    entries_count: 0,
    points: Array.from({ length: 14 }, (_, i) => ({
      date: `2026-06-${String(i + 6).padStart(2, '0')}`,
      label: i === 13 ? 'Сегодня' : 'Пн',
      mood_score: null,
    })),
  };
  diaryApi.getDiarySummary.mockResolvedValue(allNullSummary);
  render(<StudentHome />);
  expect(await screen.findByText(/пока нет записей/i)).toBeInTheDocument();
});

// ─── new: today entry state ───────────────────────────────────────────────────

test('shows empty CTA when no today diary entry', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_NO_ENTRY);
  render(<StudentHome />);
  expect(await screen.findByText(/Сегодня состояние ещё не отмечено/i)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Отметить состояние/i })).toHaveAttribute('href', '/student/diary');
});

test('shows today mood score and word when entry exists', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY);
  render(<StudentHome />);
  // mood_score=7 → "Хорошо"; score number "7" appears; "Дополнить запись" CTA
  expect(await screen.findByText('Хорошо')).toBeInTheDocument();
  expect(screen.getByText('7')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Дополнить запись/i })).toHaveAttribute('href', '/student/diary');
});

test('Запись сегодня stat card shows Нет when no entry', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_NO_ENTRY);
  render(<StudentHome />);
  expect(await screen.findByText('Запись сегодня')).toBeInTheDocument();
  // value transitions from '…' to 'Нет' after getTodayDiaryEntry resolves
  expect(await screen.findByText('Нет')).toBeInTheDocument();
});

test('Запись сегодня stat card shows Есть when entry exists', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY);
  render(<StudentHome />);
  expect(await screen.findByText('Запись сегодня')).toBeInTheDocument();
  expect(await screen.findByText('Есть')).toBeInTheDocument();
});

// ─── new: removed fake/mock content ──────────────────────────────────────────

test('does not render hardcoded anxiety metric (Тревожность 3.2)', () => {
  render(<StudentHome />);
  expect(screen.queryByText('Тревожность')).not.toBeInTheDocument();
  expect(screen.queryByText('3.2')).not.toBeInTheDocument();
});

test('does not render hardcoded sleep metric (Сон 7.4)', () => {
  render(<StudentHome />);
  expect(screen.queryByText('Сон')).not.toBeInTheDocument();
  expect(screen.queryByText('7.4')).not.toBeInTheDocument();
});

test('does not render hardcoded session with Мария Ковалёва or April 30', () => {
  render(<StudentHome />);
  expect(screen.queryByText('Мария Ковалёва')).not.toBeInTheDocument();
  expect(screen.queryByText(/30 апреля/i)).not.toBeInTheDocument();
});

test('does not render GAD-7 quick action', () => {
  render(<StudentHome />);
  expect(screen.queryByText(/GAD-7/i)).not.toBeInTheDocument();
});

test('does not render mood slider input range on home page', () => {
  render(<StudentHome />);
  expect(screen.queryByRole('slider')).not.toBeInTheDocument();
});

test('getTodayDiaryEntry is called on mount', async () => {
  render(<StudentHome />);
  await waitFor(() =>
    expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1)
  );
});
