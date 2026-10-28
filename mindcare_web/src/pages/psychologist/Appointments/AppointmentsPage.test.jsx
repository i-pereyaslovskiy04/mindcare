import { fireEvent, render, screen } from '@testing-library/react';
import PsychologistAppointmentsPage from './AppointmentsPage';

// Интеграция вкладок с shared Tabs: данные и тяжёлые панели — заглушки.
// В подписи «Индивидуальные» мягкий перенос (U+00AD) — сравниваем без него.
const INDIVIDUAL = /^Индивиду\u00ad?альные$/;
const labels = () => screen.getAllByRole('tab').map((tab) => tab.textContent.replace(/\u00ad/g, ''));
jest.mock('../../../features/psychologist/hooks/usePsychologistAppointments', () => ({
  usePsychologistAppointments: () => ({
    items: [], total: 0, loading: false, error: null, page: 1,
    setPage: () => {}, statusFilter: 'all', setFilter: () => {}, refetch: () => {},
  }),
}));
jest.mock('../../../features/psychologist/hooks/usePsychologistCalendarRange', () => ({
  usePsychologistCalendarMonth: () => ({ eventsByDay: {}, loading: false, refetch: () => {} }),
}));
jest.mock('./PsychologistCalendar', () => function CalendarStub() {
  return <div>CALENDAR</div>;
});
jest.mock('./GroupSessionsPanel', () => function GroupStub() {
  return <div>GROUP_SESSIONS</div>;
});
jest.mock('./ScheduleTab', () => function ScheduleStub() {
  return <div>SCHEDULE</div>;
});

test('вкладки сессий — shared Tabs: подпись, три раздела, по умолчанию «Индивидуальные»', () => {
  render(<PsychologistAppointmentsPage />);
  expect(screen.getByRole('tablist', { name: 'Разделы сессий' })).toBeInTheDocument();
  expect(labels()).toEqual(['Индивидуальные', 'Групповые', 'Моё расписание']);
  const individual = screen.getByRole('tab', { name: INDIVIDUAL });
  expect(individual).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByRole('tabpanel', { name: INDIVIDUAL })).toHaveTextContent('CALENDAR');
  expect(screen.queryByText('GROUP_SESSIONS')).toBeNull();
  expect(screen.queryByText('SCHEDULE')).toBeNull();
});

test('переключение показывает только содержимое выбранной вкладки', () => {
  render(<PsychologistAppointmentsPage />);
  fireEvent.click(screen.getByRole('tab', { name: 'Групповые' }));
  expect(screen.getByRole('tab', { name: 'Групповые' })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByRole('tabpanel', { name: 'Групповые' })).toHaveTextContent('GROUP_SESSIONS');
  expect(screen.queryByText('CALENDAR')).toBeNull();

  fireEvent.click(screen.getByRole('tab', { name: 'Моё расписание' }));
  expect(screen.getByRole('tabpanel', { name: 'Моё расписание' })).toHaveTextContent('SCHEDULE');
  expect(screen.queryByText('GROUP_SESSIONS')).toBeNull();
});

test('каждая вкладка ссылается на свою панель (aria-controls ↔ aria-labelledby)', () => {
  render(<PsychologistAppointmentsPage />);
  screen.getAllByRole('tab').forEach((tab) => {
    const panelId = tab.getAttribute('aria-controls');
    // Скрытые панели тоже в DOM — связь действительна для всех вкладок.
    const panel = screen.getAllByRole('tabpanel', { hidden: true }).find((p) => p.id === panelId);
    expect(panel).toBeDefined();
    expect(panel).toHaveAttribute('aria-labelledby', tab.id);
  });
});
