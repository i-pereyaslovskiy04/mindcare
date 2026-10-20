import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import * as api from '../../../../api/users.api';
import UserLifecycleDialog, { DEACTIVATION_REASON_MAX_LEN } from './UserLifecycleDialog';

jest.mock('../../../../api/users.api');

const USER = { uuid: 'u-42', full_name: 'Пётр Петров' };

function renderDialog(mode, props = {}) {
  const onDone = jest.fn();
  const onClose = jest.fn();
  render(
    <UserLifecycleDialog
      open
      mode={mode}
      userInfo={USER}
      onClose={onClose}
      onDone={onDone}
      {...props}
    />,
  );
  return { onDone, onClose };
}

beforeEach(() => {
  api.deactivateUser.mockResolvedValue({});
  api.restoreUser.mockResolvedValue({});
});

test('deactivate: empty or whitespace-only reason blocks submit', () => {
  renderDialog('deactivate');
  const submit = screen.getByRole('button', { name: 'Отключить аккаунт' });

  fireEvent.click(submit);
  expect(screen.getByRole('alert')).toHaveTextContent('Укажите причину отключения');
  expect(api.deactivateUser).not.toHaveBeenCalled();

  fireEvent.change(screen.getByLabelText('Причина отключения'), {
    target: { value: '    ' },
  });
  fireEvent.click(submit);
  expect(api.deactivateUser).not.toHaveBeenCalled();
});

test('deactivate: sends trimmed reason, then calls onDone', async () => {
  const { onDone } = renderDialog('deactivate');
  fireEvent.change(screen.getByLabelText('Причина отключения'), {
    target: { value: '  Увольнение  ' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Отключить аккаунт' }));

  await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
  expect(api.deactivateUser).toHaveBeenCalledWith('u-42', 'Увольнение');
});

test('deactivate: explains that data and email are kept and only admin restores', () => {
  renderDialog('deactivate');
  const text = screen.getByText(/связанные данные сохранятся/);
  expect(text).toHaveTextContent('email');
  expect(text).toHaveTextContent('только администратор');
  expect(screen.getByLabelText('Причина отключения')).toHaveAttribute(
    'maxLength', String(DEACTIVATION_REASON_MAX_LEN),
  );
});

test('deactivate: server error is shown and dialog stays open', async () => {
  api.deactivateUser.mockRejectedValueOnce(new Error('Нельзя отключить собственный аккаунт'));
  const { onDone } = renderDialog('deactivate');
  fireEvent.change(screen.getByLabelText('Причина отключения'), {
    target: { value: 'Причина' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Отключить аккаунт' }));

  expect(await screen.findByText('Нельзя отключить собственный аккаунт')).toBeInTheDocument();
  expect(onDone).not.toHaveBeenCalled();
});

test('restore: confirms without a reason field', async () => {
  const { onDone } = renderDialog('restore');
  expect(screen.queryByLabelText('Причина отключения')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Восстановить' }));

  await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
  expect(api.restoreUser).toHaveBeenCalledWith('u-42');
  expect(api.deactivateUser).not.toHaveBeenCalled();
});
