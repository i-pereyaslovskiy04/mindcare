import { useState } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ForgotPasswordModal from './ForgotPasswordModal';
import { passwordResetConfirm, passwordResetInit } from '../../../api/auth.api';

jest.mock('../../../api/auth.api');
jest.mock('./components/OTPInput', () => function OTPInputStub({ onChange }) {
  return (
    <button type="button" onClick={() => onChange(['1', '2', '3', '4', '5', '6'])}>
      Ввести код
    </button>
  );
});

function deferred() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function Harness(props) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Открыть</button>
      <ForgotPasswordModal open={open} onClose={() => setOpen(false)} {...props} />
    </>
  );
}

async function goToPasswordStep({ typeEmail = true } = {}) {
  if (typeEmail) await userEvent.type(screen.getByLabelText('Электронная почта'), 'me@example.org');
  await userEvent.click(screen.getByRole('button', { name: 'Отправить код' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Ввести код' }));
  await screen.findByLabelText('Новый пароль');
}

async function fillPasswords(value = 'new-password-1') {
  await userEvent.type(screen.getByLabelText('Новый пароль'), value);
  await userEvent.type(screen.getByLabelText(/Повторите|Подтверд/), value);
}

describe('ForgotPasswordModal', () => {
  beforeEach(() => {
    passwordResetInit.mockResolvedValue({});
  });

  it('публичный сценарий: email редактируемый, шаг «готово», колбэка нет', async () => {
    passwordResetConfirm.mockResolvedValue({});
    render(<Harness />);
    const email = screen.getByLabelText('Электронная почта');
    expect(email).not.toHaveAttribute('readonly');
    await goToPasswordStep();
    await fillPasswords();
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить пароль' }));
    expect(await screen.findByText(/изменён/)).toBeInTheDocument();
    expect(passwordResetConfirm).toHaveBeenCalledWith({
      email: 'me@example.org', code: '123456', new_password: 'new-password-1',
    });
    await userEvent.click(screen.getByRole('button', { name: 'Войти в аккаунт' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('initialEmail + emailLocked: email подставлен и не редактируется', async () => {
    render(<Harness initialEmail="owner@example.org" emailLocked />);
    const email = screen.getByLabelText('Электронная почта');
    expect(email).toHaveValue('owner@example.org');
    expect(email).toHaveAttribute('readonly');
    await userEvent.click(screen.getByRole('button', { name: 'Отправить код' }));
    await waitFor(() => expect(passwordResetInit).toHaveBeenCalledWith({ email: 'owner@example.org' }));
  });

  it('onCompleted вызывается один раз сразу после подтверждения', async () => {
    passwordResetConfirm.mockResolvedValue({});
    const onCompleted = jest.fn();
    render(<Harness initialEmail="owner@example.org" emailLocked onCompleted={onCompleted} />);
    await goToPasswordStep({ typeEmail: false });
    await fillPasswords();
    expect(onCompleted).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить пароль' }));
    await waitFor(() => expect(onCompleted).toHaveBeenCalledTimes(1));
    // окно ещё открыто; закрытие после завершения вызов не дублирует
    await userEvent.click(await screen.findByRole('button', { name: 'Войти в аккаунт' }));
    expect(onCompleted).toHaveBeenCalledTimes(1);
  });

  it('закрытие окна во время финального запроса не теряет результат', async () => {
    const pending = deferred();
    passwordResetConfirm.mockReturnValue(pending.promise);
    const onCompleted = jest.fn();
    render(<Harness initialEmail="owner@example.org" emailLocked onCompleted={onCompleted} />);
    await goToPasswordStep({ typeEmail: false });
    await fillPasswords();
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить пароль' }));
    await waitFor(() => expect(passwordResetConfirm).toHaveBeenCalledTimes(1));

    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(onCompleted).not.toHaveBeenCalled();

    await act(async () => { pending.resolve({}); });
    expect(onCompleted).toHaveBeenCalledTimes(1);
    // после запоздалого ответа окно остаётся закрытым и сброшенным
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('повторная отправка во время запроса не даёт второго вызова', async () => {
    const pending = deferred();
    passwordResetConfirm.mockReturnValue(pending.promise);
    const onCompleted = jest.fn();
    render(<Harness initialEmail="owner@example.org" emailLocked onCompleted={onCompleted} />);
    await goToPasswordStep({ typeEmail: false });
    await fillPasswords();
    const save = screen.getByRole('button', { name: 'Сохранить пароль' });
    await userEvent.click(save);
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard('{Enter}');
    await act(async () => { pending.resolve({}); });
    expect(passwordResetConfirm).toHaveBeenCalledTimes(1);
    expect(onCompleted).toHaveBeenCalledTimes(1);
  });

  it('ошибка подтверждения возвращает на шаг кода и не вызывает onCompleted', async () => {
    passwordResetConfirm.mockRejectedValue(new Error('Неверный код'));
    const onCompleted = jest.fn();
    render(<Harness initialEmail="owner@example.org" emailLocked onCompleted={onCompleted} />);
    await goToPasswordStep({ typeEmail: false });
    await fillPasswords();
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить пароль' }));
    expect(await screen.findByText('Неверный код')).toBeInTheDocument();
    expect(onCompleted).not.toHaveBeenCalled();
  });
});
