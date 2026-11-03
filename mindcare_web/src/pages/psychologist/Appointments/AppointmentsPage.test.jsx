import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { usePsychologistAppointments } from '../../../features/psychologist/hooks/usePsychologistAppointments';
import { usePsychologistCalendarMonth } from '../../../features/psychologist/hooks/usePsychologistCalendarRange';
import { markAppointmentOutcome } from '../../../api/appointments.api';
import AppointmentsPage from './AppointmentsPage';

jest.mock('../../../features/psychologist/hooks/usePsychologistAppointments');
jest.mock('../../../features/psychologist/hooks/usePsychologistCalendarRange');
jest.mock('../../../api/appointments.api');

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
