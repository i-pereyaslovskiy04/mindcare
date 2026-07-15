import { renderHook, waitFor, act } from '@testing-library/react';
import * as api from '../../../../api/users.api';
import { useUserForm } from './useUserForm';

jest.mock('../../../../api/users.api');

beforeEach(() => {
  api.getUser.mockResolvedValue({
    full_name: 'Иван Петров',
    phone: '+7 900 000-00-00',
    roles: ['psychologist'],
    role: 'psychologist',
    is_active: true,
  });
  api.updateUser.mockResolvedValue({});
  api.createUser.mockResolvedValue({});
});

function toggle(result, role) {
  act(() => { result.current.toggleRole(role); });
}
function set(result, name, value, type = 'text') {
  act(() => {
    result.current.handleChange({ target: { name, value, type } });
  });
}
function setChecked(result, name, checked) {
  act(() => {
    result.current.handleChange({ target: { name, type: 'checkbox', checked } });
  });
}
function submit(result) {
  act(() => { result.current.handleSubmit({ preventDefault() {} }); });
}

// ─── EDIT ────────────────────────────────────────────────────────────────────

test('edit without role change sends only profile fields, no roles/legal basis', async () => {
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  submit(result);

  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  const [uuidArg, payload] = api.updateUser.mock.calls[0];
  expect(uuidArg).toBe('u1');
  expect(payload).toEqual({
    full_name: 'Иван Петров',
    phone: '+7 900 000-00-00',
    is_active: true,
  });
  expect(payload).not.toHaveProperty('roles');
  expect(payload).not.toHaveProperty('legal_basis_confirmed');
});

test('adding a staff role WITHOUT legal basis → validation error, no request', async () => {
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  toggle(result, 'supervisor'); // add supervisor to psychologist
  expect(result.current.editNeedsBasis).toBe(true);
  submit(result);

  expect(result.current.errors.legal_basis_confirmed).toBeTruthy();
  expect(result.current.errors.basis_reference).toBeTruthy();
  expect(api.updateUser).not.toHaveBeenCalled();
});

test('add supervisor to psychologist with legal basis → roles[] + legal basis', async () => {
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  toggle(result, 'supervisor');
  set(result, 'basis_type', 'employment');
  set(result, 'basis_reference', 'приказ №7');
  setChecked(result, 'legal_basis_confirmed', true);
  submit(result);

  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  const [, payload] = api.updateUser.mock.calls[0];
  expect(payload.roles).toEqual(
    expect.arrayContaining(['psychologist', 'supervisor']),
  );
  expect(payload.roles).toHaveLength(2);
  expect(payload.legal_basis_confirmed).toBe(true);
  expect(payload.basis_type).toBe('employment');
  expect(payload.basis_reference).toBe('приказ №7');
});

test('removing a staff role does NOT require legal basis', async () => {
  api.getUser.mockResolvedValueOnce({
    full_name: 'Мульти Роль', phone: '',
    roles: ['psychologist', 'supervisor'], is_active: true,
  });
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  toggle(result, 'supervisor'); // remove supervisor
  expect(result.current.editNeedsBasis).toBe(false);
  submit(result);

  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  const [, payload] = api.updateUser.mock.calls[0];
  expect(payload.roles).toEqual(['psychologist']);
  expect(payload).not.toHaveProperty('legal_basis_confirmed');
});

test('existing student is preserved read-only and NOT sent in payload', async () => {
  api.getUser.mockResolvedValueOnce({
    full_name: 'Студент Психолог', phone: '',
    roles: ['student', 'psychologist'], is_active: true,
  });
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  expect(result.current.hasStudent).toBe(true);
  // staff-контрол управляет только staff-набором — student не в values.roles
  expect(result.current.values.roles).toEqual(['psychologist']);

  toggle(result, 'supervisor');
  set(result, 'basis_type', 'employment');
  set(result, 'basis_reference', 'приказ №9');
  setChecked(result, 'legal_basis_confirmed', true);
  submit(result);

  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  const [, payload] = api.updateUser.mock.calls[0];
  expect(payload.roles).not.toContain('student');
  expect(payload.roles).toEqual(
    expect.arrayContaining(['psychologist', 'supervisor']),
  );
});

test('empty staff set for a non-student user → validation error', async () => {
  api.getUser.mockResolvedValueOnce({
    full_name: 'Один Психолог', phone: '', roles: ['psychologist'], is_active: true,
  });
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  toggle(result, 'psychologist'); // remove the only role
  submit(result);

  expect(result.current.errors.roles).toBeTruthy();
  expect(api.updateUser).not.toHaveBeenCalled();
});

test('edit submit sends phone in masked format', async () => {
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  set(result, 'phone', '9491234567');
  submit(result);

  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  const [, payload] = api.updateUser.mock.calls[0];
  expect(payload.phone).toBe('+7 (949) 123-45-67');
  expect(payload).not.toHaveProperty('roles');
});

// ─── Staff-набор политика (backend: added-без-current_staff → 422) ───────────

test('student-only: scalar edit succeeds without touching roles', async () => {
  api.getUser.mockResolvedValueOnce({
    full_name: 'Студент Иванов', phone: '',
    roles: ['student'], is_active: true,
  });
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  expect(result.current.canManageStaffRoles).toBe(false);
  set(result, 'full_name', 'Студент Иванов (обновлено)');
  submit(result);

  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  const [, payload] = api.updateUser.mock.calls[0];
  expect(payload).toEqual({
    full_name: 'Студент Иванов (обновлено)',
    phone: '',
    is_active: true,
  });
  expect(payload).not.toHaveProperty('roles');
});

test('student-only: staff checkbox cannot be toggled, no request with a new role', async () => {
  api.getUser.mockResolvedValueOnce({
    full_name: 'Студент Иванов', phone: '',
    roles: ['student'], is_active: true,
  });
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  toggle(result, 'psychologist'); // guarded no-op: canManageStaffRoles === false
  expect(result.current.values.roles).toEqual([]);

  submit(result);
  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  const [, payload] = api.updateUser.mock.calls[0];
  expect(payload).not.toHaveProperty('roles');
});

test('roleless user (roles: []) can perform a scalar-only edit', async () => {
  api.getUser.mockResolvedValueOnce({
    full_name: 'Без Роли', phone: '', roles: [], is_active: true,
  });
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  expect(result.current.canManageStaffRoles).toBe(false);
  submit(result); // без изменений — unchanged empty roles не должен блокировать

  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  expect(result.current.errors.roles).toBeUndefined();
  const [, payload] = api.updateUser.mock.calls[0];
  expect(payload).not.toHaveProperty('roles');
});

test('student+staff can remove the last staff role, keeping student', async () => {
  api.getUser.mockResolvedValueOnce({
    full_name: 'Студент Психолог', phone: '',
    roles: ['student', 'psychologist'], is_active: true,
  });
  const { result } = renderHook(() =>
    useUserForm({ mode: 'edit', uuid: 'u1', onSuccess: jest.fn() }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  expect(result.current.canManageStaffRoles).toBe(true);
  toggle(result, 'psychologist'); // remove the only staff role
  submit(result);

  await waitFor(() => expect(api.updateUser).toHaveBeenCalledTimes(1));
  const [, payload] = api.updateUser.mock.calls[0];
  expect(payload.roles).toEqual([]);
  expect(result.current.errors.roles).toBeUndefined();
});

// ─── CREATE ──────────────────────────────────────────────────────────────────

test('create sends roles[] + requires non-empty basis_reference', async () => {
  const { result } = renderHook(() =>
    useUserForm({ mode: 'create', onSuccess: jest.fn() }),
  );

  set(result, 'full_name', 'Новый Сотрудник');
  set(result, 'email', 'new@example.com');
  set(result, 'basis_type', 'employment');
  setChecked(result, 'legal_basis_confirmed', true);

  // basis_reference пустой → ошибка, запроса нет
  submit(result);
  expect(result.current.errors.basis_reference).toBeTruthy();
  expect(api.createUser).not.toHaveBeenCalled();

  set(result, 'basis_reference', 'приказ №1');
  submit(result);

  await waitFor(() => expect(api.createUser).toHaveBeenCalledTimes(1));
  const [payload] = api.createUser.mock.calls[0];
  expect(payload.roles).toEqual(['psychologist']);
  expect(payload).not.toHaveProperty('role');
  expect(payload.basis_reference).toBe('приказ №1');
  expect(payload.legal_basis_confirmed).toBe(true);
});

test('create with multiple staff roles sends both', async () => {
  const { result } = renderHook(() =>
    useUserForm({ mode: 'create', onSuccess: jest.fn() }),
  );

  set(result, 'full_name', 'Мульти Стафф');
  set(result, 'email', 'multi@example.com');
  toggle(result, 'supervisor'); // adds supervisor to default psychologist
  set(result, 'basis_reference', 'приказ №2');
  setChecked(result, 'legal_basis_confirmed', true);
  submit(result);

  await waitFor(() => expect(api.createUser).toHaveBeenCalledTimes(1));
  const [payload] = api.createUser.mock.calls[0];
  expect(payload.roles).toEqual(
    expect.arrayContaining(['psychologist', 'supervisor']),
  );
});
