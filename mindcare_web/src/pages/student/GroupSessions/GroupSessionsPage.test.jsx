import { render, screen, waitFor } from '@testing-library/react';
import StudentGroupSessionsPage from './GroupSessionsPage';
import * as appointmentsApi from '../../../api/appointments.api';

jest.mock('../../../api/appointments.api');

beforeEach(() => {
  appointmentsApi.getGroupSessions.mockResolvedValue({ items: [], total: 0 });
});

test('над заголовком нет декоративной подписи роли («Пользователь»/«Студент»)', async () => {
  render(<StudentGroupSessionsPage />);
  await waitFor(() => expect(appointmentsApi.getGroupSessions).toHaveBeenCalledTimes(1));
  await screen.findByText('Нет предстоящих занятий');

  expect(screen.queryByText('Пользователь')).toBeNull();
  expect(screen.queryByText('Студент')).toBeNull();
  // заголовок страницы — контент, не подпись роли, остаётся прежним
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Групповые занятия');
});
