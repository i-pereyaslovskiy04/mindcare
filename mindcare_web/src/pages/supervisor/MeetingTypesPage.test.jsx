import { render, screen, waitFor } from '@testing-library/react';
import MeetingTypesPage from './MeetingTypesPage';
import * as api from '../../api/appointments.api';

jest.mock('../../api/appointments.api');

beforeEach(() => {
  jest.clearAllMocks();
  api.getMeetingTypes.mockResolvedValue({ items: [] });
});

// Декоративной подписи роли над заголовком нет ни в одном кабинете
// (страница общая для /supervisor и /admin); содержательный h1 остаётся.
test('no decorative role label above the heading', async () => {
  render(<MeetingTypesPage />);
  await waitFor(() => expect(api.getMeetingTypes).toHaveBeenCalled());
  expect(screen.queryByText('Супервизор')).toBeNull();
  expect(screen.queryByText('Администратор')).toBeNull();
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Типы встреч');
});
