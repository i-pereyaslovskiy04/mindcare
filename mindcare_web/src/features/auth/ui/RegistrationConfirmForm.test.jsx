import fs from 'fs';
import path from 'path';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import RegistrationConfirmForm, {
  ATTEMPTS_EXHAUSTED_MESSAGE, CODE_EXPIRED_MESSAGE, CONFIRM_FALLBACK_ERROR,
  REFERENCE_INVALID_MESSAGE, REFERENCE_MISSING_MESSAGE,
} from './RegistrationConfirmForm';
import * as authApi from '../../../api/auth.api';

jest.mock('../../../api/auth.api', () => ({ registerConfirm: jest.fn() }));

const SOURCE = fs.readFileSync(path.join(__dirname, 'RegistrationConfirmForm.jsx'), 'utf8');

const REF = '8a62d590-71a1-4b17-90f7-4a5ff0c9d782';
const EMAIL = 'student@donnu.ru';

function setup(props = {}) {
  const onConfirmed = jest.fn();
  const onRestart = jest.fn();
  render(
    <RegistrationConfirmForm
      registrationReference={REF}
      onConfirmed={onConfirmed}
      onRestart={onRestart}
      {...props}
    />,
  );
  return { onConfirmed, onRestart };
}

const cells = () => within(screen.getByRole('group', { name: 'Код подтверждения' })).getAllByRole('textbox');

function typeCode(digits) {
  cells().forEach((input, i) => {
    fireEvent.change(input, { target: { value: digits[i] } });
  });
}

const rejected = (message, code) => Object.assign(new Error(message), { status: 400, code });

beforeEach(() => {
  jest.clearAllMocks();
  authApi.registerConfirm.mockResolvedValue({ message: 'Регистрация завершена', email: EMAIL });
});

test('по ссылке: общий шаг кода, только код, без поля email', () => {
  setup();
  expect(screen.getByRole('heading', { name: 'Подтверждение регистрации' })).toBeInTheDocument();
  expect(screen.getByText('Введите 6-значный код из письма.')).toBeInTheDocument();
  expect(cells()).toHaveLength(6);
  expect(screen.queryByLabelText('Email')).toBeNull();
  expect(screen.queryByRole('textbox', { name: /email/i })).toBeNull();
  expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Начать регистрацию заново' })).toBeInTheDocument();
  // Reference не показывается и повторной отправки нет.
  expect(document.body).not.toHaveTextContent(REF);
  expect(screen.queryByText(/Отправить повторно/)).toBeNull();
});

test('код из 6 цифр → POST { registrationReference, code } один раз → onConfirmed(email из ответа)', async () => {
  const { onConfirmed } = setup();
  typeCode('012345');
  fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
  await waitFor(() => expect(onConfirmed).toHaveBeenCalledWith(EMAIL));
  expect(authApi.registerConfirm).toHaveBeenCalledTimes(1);
  expect(authApi.registerConfirm).toHaveBeenCalledWith({ registrationReference: REF, code: '012345' });
});

test('reference и код не попадают в storage', async () => {
  const setItem = jest.spyOn(Storage.prototype, 'setItem');
  const { onConfirmed } = setup();
  typeCode('482915');
  await waitFor(() => expect(onConfirmed).toHaveBeenCalled());
  expect(setItem).not.toHaveBeenCalled();
  setItem.mockRestore();
});

test('во время проверки ячейки недоступны', async () => {
  let resolve;
  authApi.registerConfirm.mockReturnValue(new Promise((r) => { resolve = r; }));
  setup();
  typeCode('482915');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Проверяем…' })).toBeDisabled());
  cells().forEach((cell) => expect(cell).toBeDisabled());
  resolve({ message: 'ok', email: EMAIL });
  await waitFor(() => expect(authApi.registerConfirm).toHaveBeenCalledTimes(1));
});

test('неверный код → текст backend, код очищен, фокус на первой ячейке', async () => {
  const message = 'Неверный код. Осталось попыток: 4';
  authApi.registerConfirm.mockRejectedValue(rejected(message, 'otp_invalid'));
  const { onConfirmed } = setup();
  typeCode('111111');
  const alert = await screen.findByText(message);
  expect(alert).toHaveAttribute('role', 'alert');
  cells().forEach((cell) => expect(cell).toHaveValue(''));
  await waitFor(() => expect(cells()[0]).toHaveFocus());
  expect(onConfirmed).not.toHaveBeenCalled();
});

test('ошибка без понятного текста → безопасный общий текст', async () => {
  authApi.registerConfirm.mockRejectedValue(new Error('HTTP 500'));
  setup();
  typeCode('111111');
  expect(await screen.findByText(CONFIRM_FALLBACK_ERROR)).toBeInTheDocument();
});

test.each([
  ['registration_reference_invalid', REFERENCE_INVALID_MESSAGE],
  ['otp_expired', CODE_EXPIRED_MESSAGE],
  ['otp_attempts_exhausted', ATTEMPTS_EXHAUSTED_MESSAGE],
])('код %s → терминальный экран: объяснение и «Начать регистрацию заново»', async (code, text) => {
  authApi.registerConfirm.mockRejectedValue(rejected('текст backend', code));
  const { onRestart } = setup();
  typeCode('111111');
  expect(await screen.findByText(text)).toHaveAttribute('role', 'alert');
  expect(screen.queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Начать регистрацию заново' }));
  expect(onRestart).toHaveBeenCalledTimes(1);
});

test.each([[null], [undefined], ['']])('нет reference (%p) → объяснение без поля email и без кода', (ref) => {
  const { onRestart } = setup({ registrationReference: ref });
  expect(screen.getByText(REFERENCE_MISSING_MESSAGE)).toBeInTheDocument();
  expect(screen.queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
  expect(screen.queryByLabelText('Email')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Начать регистрацию заново' }));
  expect(onRestart).toHaveBeenCalledTimes(1);
  expect(authApi.registerConfirm).not.toHaveBeenCalled();
});

test('отдельного OTP UI нет: форма использует общий RegistrationOtpStep', () => {
  expect(SOURCE).toMatch(/import RegistrationOtpStep[^;]+from '\.\/RegistrationOtpStep'/);
  expect(SOURCE).toMatch(/<RegistrationOtpStep\s/);
  expect(SOURCE).not.toMatch(/CodeInput/);
  expect(SOURCE).not.toMatch(/localStorage|sessionStorage|navigate\(/);
});

test('«Начать регистрацию заново» на шаге кода → onRestart', () => {
  const { onRestart } = setup();
  fireEvent.click(screen.getByRole('button', { name: 'Начать регистрацию заново' }));
  expect(onRestart).toHaveBeenCalledTimes(1);
});
