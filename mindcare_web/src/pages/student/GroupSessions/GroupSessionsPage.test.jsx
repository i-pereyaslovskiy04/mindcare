import { render, screen, waitFor } from '@testing-library/react';
import StudentGroupSessionsPage from './GroupSessionsPage';
import * as appointmentsApi from '../../../api/appointments.api';

jest.mock('../../../api/appointments.api');

beforeEach(() => {
  appointmentsApi.getGroupSessions.mockResolvedValue({ items: [], total: 0 });
});

test('метка кабинета — подпись роли из общей карты («Пользователь»), не «Студент»', async () => {
  render(<StudentGroupSessionsPage />);
  await waitFor(() => expect(appointmentsApi.getGroupSessions).toHaveBeenCalledTimes(1));
  await screen.findByText('Нет предстоящих занятий');

  expect(screen.getByText('Пользователь')).toBeInTheDocument();
  expect(screen.queryByText('Студент')).toBeNull();
  // заголовок страницы — контент, не подпись роли, остаётся прежним
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Групповые занятия');
});
