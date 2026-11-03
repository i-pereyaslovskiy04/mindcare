import { render, screen, waitFor, within } from '@testing-library/react';
import * as AuthContext from '../../features/auth/AuthContext';
import * as diaryApi from '../../api/diary.api';
import * as appointmentsApi from '../../api/appointments.api';
import * as assignmentsApi from '../../api/assignments.api';
import StudentHome from './StudentHome';

jest.mock('../../api/diary.api');
jest.mock('../../api/appointments.api');
jest.mock('../../api/assignments.api');
jest.mock('../../features/auth/AuthContext');
jest.mock('react-router-dom', () => ({
  useNavigate: jest.fn(() => jest.fn()),
  Link: ({ to, children, ...props }) => (
    <a href={to} {...props}>{children}</a>
  ),
}), { virtual: true });

const MOCK_SUMMARY_14D_WITH_ENTRIES = {
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

const MOCK_SUMMARY_14D_EMPTY = {
  period: '14d',
  entries_count: 0,
  points: Array.from({ length: 14 }, (_, i) => ({
    date: `2026-06-${String(i + 10).padStart(2, '0')}`,
    label: String(i + 10),
    mood_score: null,
  })),
};

const MOCK_TODAY_NO_ENTRY   = { entry_date: '2026-06-24', mood_score: null, entry_text: '', emotions: [] };
const MOCK_TODAY_WITH_ENTRY = { entry_date: '2026-06-24', mood_score: 7,    entry_text: 'Хорошо', emotions: ['calm'] };

beforeEach(() => {
  jest.clearAllMocks();
  AuthContext.useAuth.mockReturnValue({ user: { name: 'Тест Тестов' }, isImpersonating: false });
  appointmentsApi.getMyUpcomingAppointments.mockResolvedValue([]);
  assignmentsApi.getMyAssignments.mockResolvedValue({ items: [], has_more: false });
  diaryApi.getDiarySummary.mockResolvedValue(MOCK_SUMMARY_14D_WITH_ENTRIES);
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_NO_ENTRY);
  diaryApi.getDiaryEmotions.mockResolvedValue([
    { key: 'calm', label: 'Спокойно', sort_order: 1 },
    { key: 'happy', label: 'Радостно', sort_order: 2 },
  ]);
});

// ─── nextStepCard: no today entry ────────────────────────────────────────────

test('nextStepCard shows "Ваш следующий шаг" when no today entry', async () => {
  render(<StudentHome />);
  expect(await screen.findByRole('heading', { name: 'Ваш следующий шаг' })).toBeInTheDocument();
});

test('primary CTA "Отметить состояние" links to /student/diary when no today entry', async () => {
  render(<StudentHome />);
  const link = await screen.findByRole('link', { name: 'Отметить состояние' });
  expect(link).toHaveAttribute('href', '/student/diary');
});

test('secondary CTA "Открыть материалы" links to /student/materials when no today entry', async () => {
  render(<StudentHome />);
  const link = await screen.findByRole('link', { name: 'Открыть материалы' });
  expect(link).toHaveAttribute('href', '/student/materials');
});

test('nextStepCard text mentions self-observation materials when no today entry', async () => {
  render(<StudentHome />);
  expect(await screen.findByText(/материалам для самостоятельной работы/i)).toBeInTheDocument();
});

// ─── nextStepCard: today entry present ───────────────────────────────────────

test('nextStepCard shows "Сегодняшняя отметка сохранена" when entry exists', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY);
  render(<StudentHome />);
  expect(await screen.findByRole('heading', { name: 'Сегодняшняя отметка сохранена' })).toBeInTheDocument();
});

test('nextStepCard shows mood score X/10 in text when entry exists', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY);
  render(<StudentHome />);
  expect(await screen.findByText(/Вы отметили состояние: 7\/10/)).toBeInTheDocument();
});

test('"Дополнить запись" links to /student/diary when entry exists', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY);
  render(<StudentHome />);
  const link = await screen.findByRole('link', { name: 'Дополнить запись' });
  expect(link).toHaveAttribute('href', '/student/diary');
});

test('nextStepCard secondary CTA "Написать психологу" links to /student/chat when entry exists', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY);
  render(<StudentHome />);
  await screen.findByRole('heading', { name: 'Сегодняшняя отметка сохранена' });
  const links = screen.getAllByRole('link', { name: /Написать психологу/i });
  links.forEach((l) => expect(l).toHaveAttribute('href', '/student/chat'));
});

// ─── psychologistCard ─────────────────────────────────────────────────────────

test('psychologistCard shows "Психолог" heading', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1));
  expect(screen.getByText('Психолог')).toBeInTheDocument();
});

test('psychologistCard "Написать психологу" links to /student/chat', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1));
  const links = screen.getAllByRole('link', { name: /Написать психологу/i });
  expect(links.length).toBeGreaterThanOrEqual(1);
  links.forEach((l) => expect(l).toHaveAttribute('href', '/student/chat'));
});

test('psychologistCard does not show fake date or full name', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Мария Ковалёва')).not.toBeInTheDocument();
  expect(screen.queryByText(/30 апреля/i)).not.toBeInTheDocument();
});

test('psychologistCard does not show old "Предстоящая сессия пока не назначена" text', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1));
  expect(screen.queryByText(/Предстоящая сессия пока не назначена/i)).not.toBeInTheDocument();
});

test('psychologistCard больше не обещает «информацию о встречах позже»', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1));
  expect(screen.queryByText(/появится здесь позже/i)).not.toBeInTheDocument();
});

// ─── Ближайшие встречи и активные задания ─────────────────────────────────────

const FUTURE = (h) => new Date(Date.now() + h * 3600 * 1000).toISOString();

test('«Ближайшие встречи»: рендерит выборку сервера как есть (по возрастанию, уже не больше трёх)', async () => {
  // Фильтрация и сортировка — на сервере (/api/appointments/my/upcoming);
  // хук и компонент только отображают то, что вернул API.
  appointmentsApi.getMyUpcomingAppointments.mockResolvedValue([
    { uuid: 'a1', status: 'pending_confirmation', starts_at: FUTURE(24), meeting_type_name: 'Первая' },
    { uuid: 'a2', status: 'confirmed', starts_at: FUTURE(48), meeting_type_name: 'Вторая' },
    { uuid: 'a4', status: 'pending_confirmation', starts_at: FUTURE(96), meeting_type_name: 'Четвёртая' },
  ]);
  render(<StudentHome />);
  const card = await screen.findByRole('region', { name: 'Ближайшие встречи' });
  const rows = await within(card).findAllByRole('listitem');
  expect(rows.map((r) => r.textContent)).toEqual([
    expect.stringContaining('Первая · ожидает подтверждения'),
    expect.stringContaining('Вторая · подтверждена'),
    expect.stringContaining('Четвёртая'),
  ]);
  expect(within(card).queryByText(/Отменённая|Прошедшая|Пятая/)).toBeNull();
  expect(appointmentsApi.getMyUpcomingAppointments).toHaveBeenCalledWith({ limit: 3 });
  expect(within(card).getByRole('link', { name: 'Открыть календарь' }))
    .toHaveAttribute('href', '/student/calendar');
});

test('«Ближайшие встречи»: пусто — честное сообщение', async () => {
  render(<StudentHome />);
  const card = await screen.findByRole('region', { name: 'Ближайшие встречи' });
  expect(await within(card).findByText('Запланированных встреч нет.')).toBeInTheDocument();
});

test('«Активные задания»: первые три открытых, ссылка на задания', async () => {
  assignmentsApi.getMyAssignments.mockResolvedValue({
    items: [
      { uuid: 't1', text: 'Прочитать материал', due_date: '2026-11-10' },
      { uuid: 't2', text: 'Записать мысли', due_date: null },
    ],
    has_more: false,
  });
  render(<StudentHome />);
  const card = await screen.findByRole('region', { name: 'Активные задания' });
  expect(await within(card).findByText('Прочитать материал')).toBeInTheDocument();
  expect(within(card).getByText(/до 10 ноября 2026/)).toBeInTheDocument();
  expect(within(card).getByText('Записать мысли')).toBeInTheDocument();
  expect(assignmentsApi.getMyAssignments).toHaveBeenCalledWith({ view: 'open', size: 3 });
  expect(within(card).getByRole('link', { name: 'Открыть задания' }))
    .toHaveAttribute('href', '/student/tasks');
});

test('«Активные задания» при входе под именем пользователя: без запроса, одно сообщение', async () => {
  AuthContext.useAuth.mockReturnValue({ user: { name: 'Тест Тестов' }, isImpersonating: true });
  render(<StudentHome />);
  const card = await screen.findByRole('region', { name: 'Активные задания' });
  expect(within(card).getByText('Задания недоступны при входе под именем пользователя.')).toBeInTheDocument();
  expect(within(card).queryByRole('link')).toBeNull();
  await waitFor(() => expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalled());
  expect(assignmentsApi.getMyAssignments).not.toHaveBeenCalled();
});

// ─── wellbeingCard ────────────────────────────────────────────────────────────

test('wellbeingCard shows "Самочувствие" heading', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1));
  expect(screen.getByText('Самочувствие')).toBeInTheDocument();
});

test('wellbeingCard shows "Сегодня ещё нет отметки" when no today entry', async () => {
  render(<StudentHome />);
  expect(await screen.findByText('Сегодня ещё нет отметки.')).toBeInTheDocument();
});

test('wellbeingCard "Отметить" links to /student/diary when no today entry', async () => {
  render(<StudentHome />);
  const link = await screen.findByRole('link', { name: 'Отметить' });
  expect(link).toHaveAttribute('href', '/student/diary');
});

test('wellbeingCard shows mood score when today entry exists', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY);
  render(<StudentHome />);
  expect(await screen.findByText(/Сегодня: 7\/10/)).toBeInTheDocument();
});

test('wellbeingCard shows emotion labels when today entry has emotions', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY);
  render(<StudentHome />);
  expect(await screen.findByText('Спокойно')).toBeInTheDocument();
});

test('wellbeingCard "Открыть дневник" links to /student/diary when entry exists', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_WITH_ENTRY);
  render(<StudentHome />);
  const links = await screen.findAllByRole('link', { name: /Открыть дневник/i });
  links.forEach((l) => expect(l).toHaveAttribute('href', '/student/diary'));
});

// ─── materialsCard ────────────────────────────────────────────────────────────

test('materialsCard shows "Материалы" heading', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1));
  expect(screen.getByText('Материалы')).toBeInTheDocument();
});

test('materialsCard "Открыть" links to /student/materials', async () => {
  render(<StudentHome />);
  const link = await screen.findByRole('link', { name: 'Открыть' });
  expect(link).toHaveAttribute('href', '/student/materials');
});

// ─── observationCard ──────────────────────────────────────────────────────────

test('observationCard is NOT shown when entries_count = 0', async () => {
  diaryApi.getDiarySummary.mockResolvedValue(MOCK_SUMMARY_14D_EMPTY);
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Самонаблюдение за 14 дней')).not.toBeInTheDocument();
});

test('observationCard IS shown when entries_count > 0', async () => {
  render(<StudentHome />);
  expect(await screen.findByText('Самонаблюдение за 14 дней')).toBeInTheDocument();
});

test('observationCard shows entries count when visible', async () => {
  render(<StudentHome />);
  await screen.findByText('Самонаблюдение за 14 дней');
  expect(screen.getByText(/3 записи/)).toBeInTheDocument();
});

test('observationCard shows sparse-data insight for 1–3 entries', async () => {
  render(<StudentHome />);
  expect(await screen.findByText(/Пока мало данных для тренда/)).toBeInTheDocument();
});

test('observationCard shows first-changes insight for 4+ entries', async () => {
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

test('observationCard "Открыть дневник" links to /student/diary', async () => {
  render(<StudentHome />);
  await screen.findByText('Самонаблюдение за 14 дней');
  const links = screen.getAllByRole('link', { name: /Открыть дневник/i });
  links.forEach((l) => expect(l).toHaveAttribute('href', '/student/diary'));
});

test('observationCard shows avg mood when available', async () => {
  render(<StudentHome />);
  await screen.findByText('Самонаблюдение за 14 дней');
  expect(screen.getByText(/среднее/)).toBeInTheDocument();
});

// ─── api calls ────────────────────────────────────────────────────────────────

test('getTodayDiaryEntry is called on mount', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1));
});

test('getDiarySummary is called with "14d" on mount', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('14d'));
});

// ─── removed old panels ───────────────────────────────────────────────────────

test('old panel heading "Моё состояние" is not rendered', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Моё состояние')).not.toBeInTheDocument();
});

// ─── приветствие: нейтральное, ФИО не разбирается ────────────────────────────

test('приветствие нейтральное: первое слово ФИО (фамилия) не выводится', async () => {
  AuthContext.useAuth.mockReturnValue({ user: { name: 'Иванова Анна Петровна' }, isImpersonating: false });
  render(<StudentHome />);
  const heading = await screen.findByRole('heading', { level: 1 });
  expect(heading).toHaveTextContent('Здравствуйте!');
  expect(heading).not.toHaveTextContent('Иванова');
  await screen.findByText('Самонаблюдение за 14 дней');   // дождаться загрузки данных
});

test('old panel heading "Поддержка" is not rendered', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Поддержка')).not.toBeInTheDocument();
});

test('"Записей за 14 дней" stat label is not rendered as a standalone block', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Записей за 14 дней')).not.toBeInTheDocument();
});

test('"Запись сегодня" stat label is not rendered as a standalone block', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Запись сегодня')).not.toBeInTheDocument();
});

test('"Нет" is not shown as a standalone mini stat value when no today entry', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_TODAY_NO_ENTRY);
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Нет')).not.toBeInTheDocument();
});

test('"Состояние сегодня" section label is not rendered (old panel structure removed)', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Состояние сегодня')).not.toBeInTheDocument();
});

// ─── removed fake / mock content ─────────────────────────────────────────────

test('does not render MoodChart or period chip buttons', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Динамика настроения')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Месяц' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Год' })).not.toBeInTheDocument();
});

test('does not render hardcoded anxiety or sleep metrics', async () => {
  render(<StudentHome />);
  expect(screen.queryByText('Тревожность')).not.toBeInTheDocument();
  expect(screen.queryByText('3.2')).not.toBeInTheDocument();
  expect(screen.queryByText('Сон')).not.toBeInTheDocument();
  expect(screen.queryByText('7.4')).not.toBeInTheDocument();
});

test('does not render GAD-7 quick action', async () => {
  render(<StudentHome />);
  expect(screen.queryByText(/GAD-7/i)).not.toBeInTheDocument();
});

test('does not render mood slider on home page', async () => {
  render(<StudentHome />);
  expect(screen.queryByRole('slider')).not.toBeInTheDocument();
});

test('old heading "Связь и действия" is not rendered', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Связь и действия')).not.toBeInTheDocument();
});

test('old heading "Быстрые действия" is not rendered', async () => {
  render(<StudentHome />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Быстрые действия')).not.toBeInTheDocument();
});
