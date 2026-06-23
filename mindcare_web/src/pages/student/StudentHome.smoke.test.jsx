import { render, screen, waitFor } from '@testing-library/react';
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

// Fixed 14-slot frame: 3 entries, rest null
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
  ].slice(0, 14),
};

const MOCK_TODAY_NO_ENTRY   = { entry_date: '2026-06-23', mood_score: null, entry_text: '', emotions: [] };
const MOCK_TODAY_WITH_ENTRY = { entry_date: '2026-06-23', mood_score: 7,    entry_text: 'Хорошо', emotions: ['calm'] };

beforeEach(() => {
  jest.clearAllMocks();
  AuthContext.useAuth.mockReturnValue({ user: { name: 'Тест Тестов' } });
  diaryApi.getDiarySummary.mockResolvedValue(MOCK_SUMMARY_14D);
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_NO_ENTRY);
  diaryApi.getDiaryEmotions.mockResolvedValue([
    { key: 'calm', label: 'Спокойно', sort_order: 1 },
    { key: 'happy', label: 'Радостно', sort_order: 2 },
  ]);
});

// ─── diary summary / stat cards ──────────────────────────────────────────────

test('requests summary period=14d by default on mount', async () => {
  render(<StudentHome />);
  await waitFor(() =>
    expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('14d')
  );
});

test('renders Записей в дневнике stat card after summary loads', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('14d'));
  expect(screen.getByText('Записей в дневнике')).toBeInTheDocument();
});

// ─── MoodChart and period chips removed ──────────────────────────────────────

test('MoodChart is not rendered on StudentHome', async () => {
  render(<StudentHome />);
  // "Динамика настроения" was the chart section heading — should not appear
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Динамика настроения')).not.toBeInTheDocument();
});

test('period chip buttons are not shown on StudentHome', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole('button', { name: 'Месяц' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Год' })).not.toBeInTheDocument();
});

// ─── today entry state ────────────────────────────────────────────────────────

test('shows empty CTA when no today diary entry', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_NO_ENTRY);
  render(<StudentHome />);
  expect(await screen.findByText(/Сегодня состояние ещё не отмечено/i)).toBeInTheDocument();
  // mood card CTA is a plain-text link (no icon) — getByText finds it uniquely vs the quick-action link
  expect(screen.getByText('Отметить состояние', { selector: 'a' })).toHaveAttribute('href', '/student/diary');
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

test('getTodayDiaryEntry is called on mount', async () => {
  render(<StudentHome />);
  await waitFor(() =>
    expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1)
  );
});

// ─── self-observation block ───────────────────────────────────────────────────

test('self-observation section heading is always visible', async () => {
  render(<StudentHome />);
  expect(await screen.findByText('Самонаблюдение · 14 дней')).toBeInTheDocument();
});

test('self-observation shows first-entry prompt when 0 entries in 14d', async () => {
  diaryApi.getDiarySummary.mockResolvedValue({
    period: '14d',
    entries_count: 0,
    points: Array.from({ length: 14 }, (_, i) => ({
      date: `2026-06-${String(i + 10).padStart(2, '0')}`,
      label: String(i + 10),
      mood_score: null,
    })),
  });
  render(<StudentHome />);
  expect(await screen.findByText(/Здесь появится динамика после первых отметок/)).toBeInTheDocument();
});

test('self-observation shows sparse-data hint when 1–3 entries in 14d', async () => {
  // Default mock has entries_count: 3 → "Пока мало данных..."
  render(<StudentHome />);
  expect(await screen.findByText(/Пока мало данных для тренда/)).toBeInTheDocument();
});

test('self-observation shows first-changes hint when 4+ entries in 14d', async () => {
  diaryApi.getDiarySummary.mockResolvedValue({
    period: '14d',
    entries_count: 5,
    points: Array.from({ length: 14 }, (_, i) => ({
      date: `2026-06-${String(i + 10).padStart(2, '0')}`,
      label: String(i + 10),
      mood_score: i < 5 ? 7 : null,
    })),
  });
  render(<StudentHome />);
  expect(await screen.findByText(/Можно смотреть первые изменения/)).toBeInTheDocument();
});

test('self-observation Открыть дневник link leads to /student/diary', async () => {
  render(<StudentHome />);
  // obs block always shows "Открыть дневник" once summary loads
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  const links = await screen.findAllByRole('link', { name: /Открыть дневник/i });
  expect(links.length).toBeGreaterThan(0);
  expect(links[links.length - 1]).toHaveAttribute('href', '/student/diary');
});

// ─── emotion display ──────────────────────────────────────────────────────────

test('shows emotion labels in mood card when today entry has emotions', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY); // emotions: ['calm']
  diaryApi.getDiaryEmotions.mockResolvedValue([
    { key: 'calm', label: 'Спокойно', sort_order: 1 },
  ]);
  render(<StudentHome />);
  expect(await screen.findByText('Спокойно')).toBeInTheDocument();
});

// ─── quick actions and routing ────────────────────────────────────────────────

test('Материалы quick action links to /student/materials', async () => {
  render(<StudentHome />);
  const link = await screen.findByRole('link', { name: /Материалы/i });
  expect(link).toHaveAttribute('href', '/student/materials');
});

test('shows Открыть дневник links when today entry exists', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY);
  render(<StudentHome />);
  // Both mood card and obs block show "Открыть дневник" when entry exists
  const links = await screen.findAllByRole('link', { name: /Открыть дневник/i });
  expect(links.length).toBeGreaterThanOrEqual(1);
  links.forEach((link) => expect(link).toHaveAttribute('href', '/student/diary'));
});

// ─── removed fake/mock content ───────────────────────────────────────────────

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
