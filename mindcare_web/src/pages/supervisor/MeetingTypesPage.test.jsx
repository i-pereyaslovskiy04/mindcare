import { render, screen, waitFor } from '@testing-library/react';
import MeetingTypesPage from './MeetingTypesPage';
import * as api from '../../api/appointments.api';

jest.mock('../../api/appointments.api');

beforeEach(() => {
  jest.clearAllMocks();
  api.getMeetingTypes.mockResolvedValue({ items: [] });
});

test('shows the supervisor label in the supervisor cabinet', async () => {
  render(<MeetingTypesPage cabinetRole="supervisor" />);
  await waitFor(() => expect(api.getMeetingTypes).toHaveBeenCalled());
  expect(screen.getByText('Супервизор')).toBeInTheDocument();
  expect(screen.queryByText('Администратор')).toBeNull();
});

test('shows the admin label in the admin cabinet', async () => {
  render(<MeetingTypesPage cabinetRole="admin" />);
  await waitFor(() => expect(api.getMeetingTypes).toHaveBeenCalled());
  expect(screen.getByText('Администратор')).toBeInTheDocument();
  expect(screen.queryByText('Супервизор')).toBeNull();
});
