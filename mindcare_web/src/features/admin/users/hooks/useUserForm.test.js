import { renderHook, waitFor, act } from '@testing-library/react';
import * as api from '../../../../api/users.api';
import { useUserForm } from './useUserForm';

jest.mock('../../../../api/users.api');

beforeEach(() => {
  api.getUser.mockResolvedValue({
    full_name: 'Иван Петров',
    phone: '+7 900 000-00-00',
    role: 'psychologist',
    is_active: true,
  });
  api.updateUser.mockResolvedValue({});
  api.createUser.mockResolvedValue({});
});

test('edit submit sends allowlisted payload WITHOUT role', async () => {
  const onSuccess = jest.fn();
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess }),
  );

  // дождаться загрузки пользователя (getUser)
  await waitFor(() => expect(result.current.loading).toBe(false));

  act(() => {
    result.current.handleSubmit({ preventDefault() {} });
  });

  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  const [uuidArg, payload] = api.updateUser.mock.calls[0];
  expect(uuidArg).toBe('u1');
  expect(payload).toEqual({
    full_name: 'Иван Петров',
    phone: '+7 900 000-00-00',
    is_active: true,
  });
  expect(payload).not.toHaveProperty('role');
});
