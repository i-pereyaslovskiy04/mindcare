import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import RegistrationConfirmForm, { CONFIRM_FALLBACK_ERROR } from './RegistrationConfirmForm';
import * as authApi from '../../../api/auth.api';

jest.mock('../../../api/auth.api', () => ({ registerConfirm: jest.fn() }));

const EMAIL = 'student@donnu.ru';

function renderForm() {
  const onConfirmed = jest.fn();
  const onRestart = jest.fn();
  render(<RegistrationConfirmForm onConfirmed={onConfirmed} onRestart={onRestart} />);
  return { onConfirmed, onRestart };
}

function typeCode(digits) {
  const group = screen.getByRole('group', { name: 'Код подтверждения' });
  within(group).getAllByRole('textbox').forEach((input, i) => {
    fireEvent.change(input, { target: { value: digits[i] } });
  });
}

const submit = () => fireEvent.click(screen.getByRole('button', { name: 'Подтвердить регистрацию' }));

beforeEach(() => {
  jest.clearAllMocks();
  authApi.registerConfirm.mockResolvedValue({ message: 'Регистрация завершена' });
});

test('открывается сам по себе: пустые email и код, без прежнего состояния', () => {
  renderForm();
  expect(screen.getByRole('heading', { name: 'Подтверждение регистрации' })).toBeInTheDocument();
  expect(screen.getByLabelText('Email')).toHaveValue('');
  const group = screen.getByRole('group', { name: 'Код подтверждения' });
  within(group).getAllByRole('textbox').forEach((input) => expect(input).toHaveValue(''));
  expect(authApi.registerConfirm).not.toHaveBeenCalled();
});

test('email и код уходят в существующий register/confirm; успех → onConfirmed(email)', async () => {
  const { onConfirmed } = renderForm();
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: `  ${EMAIL} ` } });
  typeCode('482915');
  submit();
  await waitFor(() => expect(onConfirmed).toHaveBeenCalledWith(EMAIL));
  expect(authApi.registerConfirm).toHaveBeenCalledWith({ email: EMAIL, code: '482915' });
});

test('без корректного email или полного кода запрос не уходит', () => {
  renderForm();
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'not-an-email' } });
  typeCode('48291 ');
  submit();
  expect(authApi.registerConfirm).not.toHaveBeenCalled();
  expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true');
});

test.each([
  'Срок действия кода истёк. Начните регистрацию заново',
  'Неверный код. Осталось попыток: 4',
  'Код не найден или уже использован',
])('ошибка backend показывается понятным текстом: %s', async (message) => {
  authApi.registerConfirm.mockRejectedValue(Object.assign(new Error(message), { status: 400 }));
  const { onConfirmed } = renderForm();
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: EMAIL } });
  typeCode('111111');
  submit();
  expect(await screen.findByText(message)).toHaveClass('apiError');
  expect(onConfirmed).not.toHaveBeenCalled();
  // Код очищен для повторного ввода, email остаётся.
  const group = screen.getByRole('group', { name: 'Код подтверждения' });
  within(group).getAllByRole('textbox').forEach((input) => expect(input).toHaveValue(''));
  expect(screen.getByLabelText('Email')).toHaveValue(EMAIL);
});

test('ошибка без текста → нейтральное сообщение', async () => {
  authApi.registerConfirm.mockRejectedValue(new Error('HTTP 500'));
  renderForm();
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: EMAIL } });
  typeCode('111111');
  submit();
  expect(await screen.findByText(CONFIRM_FALLBACK_ERROR)).toHaveAttribute('role', 'alert');
});

test('«Начать регистрацию заново» вызывает onRestart и не шлёт register/init', () => {
  const { onRestart } = renderForm();
  fireEvent.click(screen.getByRole('button', { name: 'Начать регистрацию заново' }));
  expect(onRestart).toHaveBeenCalledTimes(1);
  expect(authApi.registerConfirm).not.toHaveBeenCalled();
});

test('email и код не попадают в URL и браузерное хранилище', async () => {
  const setLocal = jest.spyOn(Storage.prototype, 'setItem');
  const before = window.location.href;
  const { onConfirmed } = renderForm();
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: EMAIL } });
  typeCode('482915');
  submit();
  await waitFor(() => expect(onConfirmed).toHaveBeenCalled());
  expect(setLocal).not.toHaveBeenCalled();
  expect(window.location.href).toBe(before);
  expect(window.location.href).not.toMatch(/482915|donnu/);
  setLocal.mockRestore();
});

test('тексты без длинного тире и без «аккаунт»', () => {
  const { container } = render(
    <RegistrationConfirmForm onConfirmed={jest.fn()} onRestart={jest.fn()} />,
  );
  expect(container.textContent).not.toMatch(/—|аккаунт/);
});
