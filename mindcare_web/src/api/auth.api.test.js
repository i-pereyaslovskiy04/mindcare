/**
 * Регистрация через провайдера: ticket из памяти вкладки уходит в теле, а без
 * него (null) тело ticket не содержит — backend берёт его из HttpOnly cookie
 * продолжения (/register/social). resume — всегда пустое тело.
 */
import * as client from './client';
import {
  oauthRegistrationConfirm, oauthRegistrationInit, oauthRegistrationPreview,
  oauthRegistrationResume,
} from './auth.api';

jest.mock('./client', () => ({ apiFetch: jest.fn() }));

const bodyOf = (call) => JSON.parse(call[1].body);

beforeEach(() => { client.apiFetch.mockResolvedValue({}); });

test('с ticket из памяти — ticket в теле', () => {
  oauthRegistrationInit({ ticket: 'tkt', email: 'a@b.ru' });
  oauthRegistrationPreview({ ticket: 'tkt' });
  oauthRegistrationConfirm({ ticket: 'tkt', code: '012345', consentAccepted: true });
  const [init, preview, confirm] = client.apiFetch.mock.calls;
  expect(bodyOf(init)).toEqual({ ticket: 'tkt', email: 'a@b.ru' });
  expect(bodyOf(preview)).toEqual({ ticket: 'tkt' });
  expect(bodyOf(confirm)).toEqual({ ticket: 'tkt', code: '012345', consent_accepted: true });
});

test('без ticket (cookie) — в теле нет поля ticket', () => {
  oauthRegistrationInit({ ticket: null });
  oauthRegistrationConfirm({ ticket: null, code: '012345', consentAccepted: true });
  oauthRegistrationResume();
  const [init, confirm, resume] = client.apiFetch.mock.calls;
  expect(bodyOf(init)).toEqual({});
  expect(bodyOf(confirm)).toEqual({ code: '012345', consent_accepted: true });
  expect(resume[0]).toBe('/api/auth/oauth/registration/resume');
  expect(bodyOf(resume)).toEqual({});
});
