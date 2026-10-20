import { getMyContacts, getUserContacts, saveMyContacts } from './contacts.api';
import { apiFetch } from './client';

jest.mock('./client');

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({});
});

test('чтение собственных контактов — GET без тела', () => {
  getMyContacts();
  expect(apiFetch).toHaveBeenCalledWith('/api/auth/profile/contacts');
});

test('сохранение — PUT только version и items', () => {
  const items = [{ id: 'u-1', type: 'phone', service: null, value: '+79490000000', label: null }];
  saveMyContacts({ version: 3, items, extra: 'x' });
  expect(apiFetch).toHaveBeenCalledWith('/api/auth/profile/contacts', {
    method: 'PUT',
    body: JSON.stringify({ version: 3, items }),
  });
});

test('чтение сотрудником адресуется uuid пользователя', () => {
  getUserContacts('1b4e28ba-2fa1-11d2-883f-0016d3cca427');
  expect(apiFetch).toHaveBeenCalledWith(
    '/api/staff/users/1b4e28ba-2fa1-11d2-883f-0016d3cca427/contacts',
  );
});
