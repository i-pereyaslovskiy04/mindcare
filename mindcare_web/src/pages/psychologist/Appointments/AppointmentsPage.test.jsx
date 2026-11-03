import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { usePsychologistAppointments } from '../../../features/psychologist/hooks/usePsychologistAppointments';
import { usePsychologistCalendarMonth } from '../../../features/psychologist/hooks/usePsychologistCalendarRange';
import { markAppointmentOutcome } from '../../../api/appointments.api';
import AppointmentsPage from './AppointmentsPage';

jest.mock('../../../features/psychologist/hooks/usePsychologistAppointments');
jest.mock('../../../features/psychologist/hooks/usePsychologistCalendarRange');
jest.mock('../../../api/appointments.api');

// Тяжёлые панели вкладок — заглушки: тесты вкладок проверяют только переключение,
// тест итога работает со списком встреч и в эти панели не заходит.
jest.mock('./PsychologistCalendar', () => function CalendarStub() {
  return <div>CALENDAR</div>;
});
jest.mock('./GroupSessionsPanel', () => function GroupStub() {
  return <div>GROUP_SESSIONS</div>;
});
jest.mock('./ScheduleTab', () => function ScheduleStub() {
  return <div>SCHEDULE</div>;
});

// В подписи «Индивидуальные» мягкий перенос (U+00AD) — сравниваем без него.
const INDIVIDUAL = /^Индивиду­?альные$/;
const labels = () => screen.getAllByRole('tab').map((tab) => tab.textContent.replace(/­/g, ''));

const appt = (uuid, extra = {}) => ({
  uuid, status: 'confirmed', starts_at: '2026-10-20T10:00:00+03:00',
  ends_at: '2026-10-20T10:50:00+03:00', duration_minutes: 50, modality: 'in_person',
  meeting_type_name: 'Консультация', student: { full_name: `Клиент ${uuid}`, email: '' },
  can_mark_outcome: false, ...extra,
});

let refetch;
let calRefetch;

beforeEach(() => {
  refetch = jest.fn();
  calRefetch = jest.fn();
  usePsychologistAppointments.mockReturnValue({
    items: [
      appt('past', { can_mark_outcome: true }),
      appt('future', { starts_at: '2099-01-01T10:00:00+03:00', ends_at: '2099-01-01T10:50:00+03:00' }),
      appt('done', { status: 'completed' }),
    ],
    total: 3, loading: false, error: null, page: 1, setPage: jest.fn(),
    statusFilter: '', setFilter: jest.fn(), refetch,
  });
  usePsychologistCalendarMonth.mockReturnValue({ eventsByDay: {}, loading: false, refetch: calRefetch });
});

// ── Вкладки сессий (shared Tabs) ─────────────────────────────────────────────

test('вкладки сессий — shared Tabs: подпись, три раздела, по умолчанию «Индивидуальные»', () => {
  render(<AppointmentsPage />);
  expect(screen.getByRole('tablist', { name: 'Разделы сессий' }).className).toMatch(/fill/);
  expect(labels()).toEqual(['Индивидуальные', 'Групповые', 'Моё расписание']);
  const individual = screen.getByRole('tab', { name: INDIVIDUAL });
  expect(individual).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByRole('tabpanel', { name: INDIVIDUAL })).toHaveTextContent('CALENDAR');
  expect(screen.queryByText('GROUP_SESSIONS')).toBeNull();
  expect(screen.queryByText('SCHEDULE')).toBeNull();
});

test('переключение показывает только содержимое выбранной вкладки', () => {
  render(<AppointmentsPage />);
  fireEvent.click(screen.getByRole('tab', { name: 'Групповые' }));
  expect(screen.getByRole('tab', { name: 'Групповые' })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByRole('tabpanel', { name: 'Групповые' })).toHaveTextContent('GROUP_SESSIONS');
  expect(screen.queryByText('CALENDAR')).toBeNull();

  fireEvent.click(screen.getByRole('tab', { name: 'Моё расписание' }));
  expect(screen.getByRole('tabpanel', { name: 'Моё расписание' })).toHaveTextContent('SCHEDULE');
  expect(screen.queryByText('GROUP_SESSIONS')).toBeNull();
});

test('каждая вкладка ссылается на свою панель (aria-controls ↔ aria-labelledby)', () => {
  render(<AppointmentsPage />);
  screen.getAllByRole('tab').forEach((tab) => {
    const panelId = tab.getAttribute('aria-controls');
    // Скрытые панели тоже в DOM — связь действительна для всех вкладок.
    const panel = screen.getAllByRole('tabpanel', { hidden: true }).find((p) => p.id === panelId);
    expect(panel).toBeDefined();
    expect(panel).toHaveAttribute('aria-labelledby', tab.id);
  });
});

// ── Итог встречи (ADR-035) ───────────────────────────────────────────────────

test('итог отмечается только у прошедшей подтверждённой встречи; подписи итогов', async () => {
  markAppointmentOutcome.mockResolvedValueOnce({ uuid: 'past', status: 'no_show', changed: true });
  render(<AppointmentsPage />);

  // кнопки итога — ровно у одной (прошедшей confirmed) встречи из трёх
  expect(screen.getAllByRole('button', { name: 'Неявка' })).toHaveLength(1);
  expect(screen.getAllByRole('button', { name: 'Состоялась' })).toHaveLength(1);
  // кнопка итога + бейдж статуса completed «Состоялась»
  expect(screen.getAllByText('Состоялась')).toHaveLength(2);

  userEvent.click(screen.getByRole('button', { name: 'Неявка' }));
  const dialog = screen.getByRole('dialog', { name: 'Отметить неявку клиента?' });
  userEvent.click(within(dialog).getByRole('button', { name: 'Неявка' }));
  await waitFor(() => expect(markAppointmentOutcome).toHaveBeenCalledWith('past', 'no_show'));
  await waitFor(() => expect(refetch).toHaveBeenCalled());
  expect(calRefetch).toHaveBeenCalled();
});
