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

// ─── panel headings ───────────────────────────────────────────────────────────

test('wellbeing panel heading Моё состояние is visible', async () => {
  render(<StudentHome />);
  expect(await screen.findByText('Моё состояние')).toBeInTheDocument();
});

test('support panel heading Поддержка is visible', async () => {
  render(<StudentHome />);
  expect(await screen.findByText('Поддержка')).toBeInTheDocument();
});

test('old heading Связь и действия is not rendered', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Связь и действия')).not.toBeInTheDocument();
});

test('old heading Быстрые действия is not rendered', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Быстрые действия')).not.toBeInTheDocument();
});

// ─── today section (left panel) ───────────────────────────────────────────────

test('today section label Состояние сегодня is visible', async () => {
  render(<StudentHome />);
  expect(await screen.findByText('Состояние сегодня')).toBeInTheDocument();
});

test('shows empty state when no today diary entry', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_NO_ENTRY);
  render(<StudentHome />);
  expect(await screen.findByText(/Сегодня состояние ещё не отмечено/i)).toBeInTheDocument();
  // CTA in left panel; all "Отметить состояние" links must go to /student/diary
  const links = screen.getAllByRole('link', { name: /Отметить состояние/i });
  expect(links.length).toBeGreaterThanOrEqual(1);
  links.forEach((link) => expect(link).toHaveAttribute('href', '/student/diary'));
});

test('shows today mood score and word when entry exists', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY);
  render(<StudentHome />);
  expect(await screen.findByText('Хорошо')).toBeInTheDocument();
  expect(screen.getByText('7')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Дополнить запись/i })).toHaveAttribute('href', '/student/diary');
});

test('getTodayDiaryEntry is called on mount', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1));
});

// ─── support panel: psychologist section ─────────────────────────────────────

test('support panel Психолог section label is visible', async () => {
  render(<StudentHome />);
  expect(await screen.findByText('Психолог')).toBeInTheDocument();
});

test('Написать психологу link appears exactly once and leads to /student/chat', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1));
  const links = screen.getAllByRole('link', { name: /Написать психологу/i });
  expect(links).toHaveLength(1);
  expect(links[0]).toHaveAttribute('href', '/student/chat');
});

// ─── support panel: materials section ────────────────────────────────────────

test('support panel Материалы section label is visible', async () => {
  render(<StudentHome />);
  expect(await screen.findByText('Материалы')).toBeInTheDocument();
});

test('Открыть материалы link leads to /student/materials', async () => {
  render(<StudentHome />);
  expect(await screen.findByRole('link', { name: /Открыть материалы/i })).toHaveAttribute('href', '/student/materials');
});

test('right panel does not contain Отметить состояние as quick action to /student/diary only in support', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  // All "Отметить состояние" links (if any remain from left panel) must go to diary, not chat
  const links = screen.queryAllByRole('link', { name: /Отметить состояние/i });
  links.forEach((link) => expect(link).toHaveAttribute('href', '/student/diary'));
});

// ─── self-observation section ─────────────────────────────────────────────────

test('self-observation label Самонаблюдение · 14 дней is visible', async () => {
  render(<StudentHome />);
  expect(await screen.findByText('Самонаблюдение · 14 дней')).toBeInTheDocument();
});

test('getDiarySummary is called with 14d on mount', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('14d'));
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

test('Открыть дневник link leads to /student/diary', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  const links = await screen.findAllByRole('link', { name: /Открыть дневник/i });
  expect(links.length).toBeGreaterThan(0);
  links.forEach((link) => expect(link).toHaveAttribute('href', '/student/diary'));
});

// ─── mini stats ───────────────────────────────────────────────────────────────

test('mini stat Записей за 14 дней is visible after summary loads', async () => {
  render(<StudentHome />);
  expect(await screen.findByText('Записей за 14 дней')).toBeInTheDocument();
});

test('mini stat Запись сегодня is visible', async () => {
  render(<StudentHome />);
  expect(await screen.findByText('Запись сегодня')).toBeInTheDocument();
});

test('mini stat shows Нет for Запись сегодня when no entry', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_NO_ENTRY);
  render(<StudentHome />);
  expect(await screen.findByText('Нет')).toBeInTheDocument();
});

test('mini stat shows Есть for Запись сегодня when entry exists', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY);
  render(<StudentHome />);
  expect(await screen.findByText('Есть')).toBeInTheDocument();
});

// ─── emotion display ──────────────────────────────────────────────────────────

test('shows emotion labels when today entry has emotions', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY);
  diaryApi.getDiaryEmotions.mockResolvedValue([
    { key: 'calm', label: 'Спокойно', sort_order: 1 },
  ]);
  render(<StudentHome />);
  expect(await screen.findByText('Спокойно')).toBeInTheDocument();
});

// ─── removed charts and period chips ─────────────────────────────────────────

test('MoodChart is not rendered', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Динамика настроения')).not.toBeInTheDocument();
});

test('period chip buttons are not shown', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole('button', { name: 'Месяц' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Год' })).not.toBeInTheDocument();
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

test('does not render mood slider on home page', () => {
  render(<StudentHome />);
  expect(screen.queryByRole('slider')).not.toBeInTheDocument();
});
