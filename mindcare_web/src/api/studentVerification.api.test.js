import {
  approveStudentVerification,
  getFaculties,
  getMyVerification,
  getStudentVerification,
  getStudentVerifications,
  rejectStudentVerification,
  submitMyVerification,
} from './studentVerification.api';
import { apiFetch } from './client';

jest.mock('./client');

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({});
});

test('каталог и собственный статус — GET без тела', () => {
  getFaculties();
  getMyVerification();
  expect(apiFetch).toHaveBeenNthCalledWith(1, '/api/student-verification/faculties');
  expect(apiFetch).toHaveBeenNthCalledWith(2, '/api/student-verification/me');
});

test('подача — POST только faculty_code и ticket_number (строкой, с нулями)', () => {
  submitMyVerification({ faculty_code: 'law', ticket_number: '000123', extra: 'x' });
  expect(apiFetch).toHaveBeenCalledWith('/api/student-verification/me', {
    method: 'POST',
    body: JSON.stringify({ faculty_code: 'law', ticket_number: '000123' }),
  });
});

test('список supervisor — статус, пагинация и поиск в query', () => {
  getStudentVerifications({ page: 2, size: 20, status: 'all', search: 'Иван' });
  const [url] = apiFetch.mock.calls[0];
  expect(url.startsWith('/api/supervisor/student-verifications?')).toBe(true);
  const params = new URLSearchParams(url.split('?')[1]);
  expect(Object.fromEntries(params)).toEqual({
    page: '2', size: '20', status: 'all', search: 'Иван',
  });
});

test('карточка и решения адресуются uuid конкретной заявки', () => {
  const uuid = '1b4e28ba-2fa1-11d2-883f-0016d3cca427';
  getStudentVerification(uuid);
  approveStudentVerification(uuid);
  rejectStudentVerification(uuid, 'Причина');
  expect(apiFetch).toHaveBeenNthCalledWith(1, `/api/supervisor/student-verifications/${uuid}`);
  expect(apiFetch).toHaveBeenNthCalledWith(
    2, `/api/supervisor/student-verifications/${uuid}/approve`, { method: 'POST' },
  );
  expect(apiFetch).toHaveBeenNthCalledWith(
    3, `/api/supervisor/student-verifications/${uuid}/reject`,
    { method: 'POST', body: JSON.stringify({ reason: 'Причина' }) },
  );
});
