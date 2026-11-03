import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ClientMeetings from './ClientMeetings';
import { getClientAppointments, markAppointmentOutcome } from '../../../api/appointments.api';

jest.mock('../../../api/appointments.api');

const meeting = (uuid, startsAt, extra = {}) => ({
  uuid, starts_at: startsAt, ends_at: startsAt.replace('T10:00', 'T10:50'),
  status: 'confirmed', meeting_type_name: 'Консультация', modality: 'online',
  via_card: false, can_mark_outcome: false, ...extra,
});

beforeEach(() => {
  jest.resetAllMocks();
  getClientAppointments.mockImplementation((uuid, { view, before }) => {
    if (view === 'upcoming') {
      return Promise.resolve({
        items: [meeting('u1', '2026-11-05T10:00:00+03:00')], has_more: false, next_cursor: null,
      });
    }
    if (!before) {
      return Promise.resolve({
        items: [meeting('h1', '2026-10-20T10:00:00+03:00', { can_mark_outcome: true }),
                meeting('h2', '2026-10-10T10:00:00+03:00', { status: 'pending_confirmation' })],
        has_more: true, next_cursor: 'next',
      });
    }
    return Promise.resolve({
      items: [meeting('h3', '2026-09-01T10:00:00+03:00', { status: 'no_show', via_card: true })],
      has_more: false, next_cursor: null,
    });
  });
});

test('предстоящие и история: подписи статусов, прошедшая неподтверждённая', async () => {
  render(<ClientMeetings studentUuid="c-1" />);
  const upcoming = await screen.findByRole('region', { name: 'Предстоящие' });
  expect(within(upcoming).getByText('5 ноября 2026 г., 10:00–10:50')).toBeInTheDocument();
  expect(within(upcoming).getByText('Подтверждена')).toBeInTheDocument();
  const history = screen.getByRole('region', { name: 'История' });
  await within(history).findByText('Не подтверждена');
  expect(within(history).getByText('Встреча прошла — отметьте итог.')).toBeInTheDocument();
  expect(within(upcoming).queryByRole('button', { name: 'Состоялась' })).toBeNull();
});

test('отметка итога через подтверждение; после сохранения списки перечитываются', async () => {
  markAppointmentOutcome.mockResolvedValueOnce({ uuid: 'h1', status: 'completed', changed: true });
  render(<ClientMeetings studentUuid="c-1" />);
  const history = await screen.findByRole('region', { name: 'История' });
  userEvent.click(await within(history).findByRole('button', { name: 'Состоялась' }));
  const dialog = screen.getByRole('dialog', { name: 'Отметить встречу как состоявшуюся?' });
  const calls = getClientAppointments.mock.calls.length;
  userEvent.click(within(dialog).getByRole('button', { name: 'Состоялась' }));
  await waitFor(() => expect(markAppointmentOutcome).toHaveBeenCalledWith('h1', 'completed'));
  await waitFor(() => expect(getClientAppointments.mock.calls.length).toBeGreaterThanOrEqual(calls + 2));
});

test('«Заметка» на встрече из догруженной страницы передаёт именно её', async () => {
  const onAddNote = jest.fn();
  render(<ClientMeetings studentUuid="c-1" onAddNote={onAddNote} />);
  const history = await screen.findByRole('region', { name: 'История' });
  userEvent.click(await within(history).findByRole('button', { name: 'Показать ещё' }));
  await within(history).findByText('1 сентября 2026 г., 10:00–10:50');
  const row = within(history).getAllByRole('listitem')
    .find(li => within(li).queryByText('1 сентября 2026 г., 10:00–10:50'));
  expect(within(row).getByText('Неявка')).toBeInTheDocument();
  expect(within(row).getByText(/запись по карточке/)).toBeInTheDocument();
  userEvent.click(within(row).getByRole('button', { name: 'Заметка' }));
  expect(onAddNote).toHaveBeenCalledWith({
    uuid: 'h3', starts_at: '2026-09-01T10:00:00+03:00', ends_at: '2026-09-01T10:50:00+03:00',
  });
});

test('без onAddNote кнопки «Заметка» нет', async () => {
  render(<ClientMeetings studentUuid="c-1" />);
  await screen.findByRole('region', { name: 'История' });
  await screen.findAllByText('Подтверждена');
  expect(screen.queryByRole('button', { name: 'Заметка' })).toBeNull();
});
