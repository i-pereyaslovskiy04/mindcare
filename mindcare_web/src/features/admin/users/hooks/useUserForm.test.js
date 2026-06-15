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

test('edit submit WITHOUT role change sends only profile fields, no role/legal basis', async () => {
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
  expect(payload).not.toHaveProperty('legal_basis_confirmed');
});

function changeRole(result, role) {
  act(() => {
    result.current.handleChange({ target: { name: 'role', value: role } });
  });
}

test('role change to staff WITHOUT legal_basis_confirmed → validation error, no request', async () => {
  api.getUser.mockResolvedValueOnce({
    full_name: 'Студент Один', phone: '', role: 'student', is_active: true,
  });
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  changeRole(result, 'psychologist');
  act(() => { result.current.handleSubmit({ preventDefault() {} }); });

  expect(result.current.errors.legal_basis_confirmed).toBeTruthy();
  expect(result.current.errors.basis_reference).toBeTruthy();
  expect(api.updateUser).not.toHaveBeenCalled();
});

test('role change student → psychologist with legal basis sends role + legal basis fields', async () => {
  api.getUser.mockResolvedValueOnce({
    full_name: 'Студент Два', phone: '', role: 'student', is_active: true,
  });
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  changeRole(result, 'psychologist');
  act(() => {
    result.current.handleChange({ target: { name: 'basis_type', value: 'employment' } });
  });
  act(() => {
    result.current.handleChange({ target: { name: 'basis_reference', value: 'приказ №7', type: 'text' } });
  });
  act(() => {
    result.current.handleChange({ target: { name: 'legal_basis_confirmed', type: 'checkbox', checked: true } });
  });
  act(() => { result.current.handleSubmit({ preventDefault() {} }); });

  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  const [, payload] = api.updateUser.mock.calls[0];
  expect(payload.role).toBe('psychologist');
  expect(payload.legal_basis_confirmed).toBe(true);
  expect(payload.basis_type).toBe('employment');
  expect(payload.basis_reference).toBe('приказ №7');
  expect(payload.legal_basis_comment).toBeNull();
});

test('role change staff → student does NOT require legal basis', async () => {
  api.getUser.mockResolvedValueOnce({
    full_name: 'Психолог Раз', phone: '', role: 'psychologist', is_active: true,
  });
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  changeRole(result, 'student');
  act(() => { result.current.handleSubmit({ preventDefault() {} }); });

  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  const [, payload] = api.updateUser.mock.calls[0];
  expect(payload.role).toBe('student');
  expect(payload).not.toHaveProperty('legal_basis_confirmed');
  expect(payload).not.toHaveProperty('basis_type');
});

test('role change psychologist → supervisor requires legal basis', async () => {
  api.getUser.mockResolvedValueOnce({
    full_name: 'Психолог Два', phone: '', role: 'psychologist', is_active: true,
  });
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  changeRole(result, 'supervisor');
  act(() => { result.current.handleSubmit({ preventDefault() {} }); });

  // без подтверждения основания — ошибка, запроса нет
  expect(result.current.errors.legal_basis_confirmed).toBeTruthy();
  expect(api.updateUser).not.toHaveBeenCalled();
});

test('role value is preserved on submit (not lost) after change', async () => {
  api.getUser.mockResolvedValueOnce({
    full_name: 'Админ Раз', phone: '', role: 'admin', is_active: true,
  });
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  changeRole(result, 'supervisor');
  expect(result.current.values.role).toBe('supervisor');
  expect(result.current.initialRole).toBe('admin');

  act(() => {
    result.current.handleChange({ target: { name: 'basis_type', value: 'contract' } });
  });
  act(() => {
    result.current.handleChange({ target: { name: 'basis_reference', value: 'договор №3', type: 'text' } });
  });
  act(() => {
    result.current.handleChange({ target: { name: 'legal_basis_confirmed', type: 'checkbox', checked: true } });
  });
  act(() => { result.current.handleSubmit({ preventDefault() {} }); });

  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  const [, payload] = api.updateUser.mock.calls[0];
  expect(payload.role).toBe('supervisor');
});

test('edit submit sends phone in masked format', async () => {
  const onSuccess = jest.fn();
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess }),
  );

  await waitFor(() => expect(result.current.loading).toBe(false));

  // пользователь набирает только цифры — handleChange форматирует
  act(() => {
    result.current.handleChange({
      target: { name: 'phone', value: '9491234567', type: 'text' },
    });
  });

  act(() => {
    result.current.handleSubmit({ preventDefault() {} });
  });

  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  const [, payload] = api.updateUser.mock.calls[0];
  expect(payload.phone).toBe('+7 (949) 123-45-67');
  expect(payload).not.toHaveProperty('role');
});
