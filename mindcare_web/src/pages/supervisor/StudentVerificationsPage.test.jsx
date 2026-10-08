import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import StudentVerificationsPage from './StudentVerificationsPage';
import { useAuth } from '../../features/auth/AuthContext';
import * as api from '../../api/studentVerification.api';

jest.mock('../../features/auth/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../api/studentVerification.api');

const UUID = '1b4e28ba-2fa1-11d2-883f-0016d3cca427';
const ITEM = {
  uuid: UUID,
  status: 'pending',
  faculty: { code: 'law', label: 'Юридический факультет' },
  submitted_at: '2026-10-01T09:00:00Z',
  reviewed_at: null,
  student: { uuid: 'u-1', full_name: 'Иван Тестов', email: 'ivan@donnu.ru', is_active: true },
  reviewer: null,
};
const CARD = {
  ...ITEM,
  ticket_number: '000123',
  rejection_reason: null,
  can_review: true,
  history: [],
};

function error(code, message = 'Ошибка') {
  const err = new Error(message);
  err.code = code;
  return err;
}

beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ isImpersonating: false });
  api.getStudentVerifications.mockResolvedValue({ items: [ITEM], total: 1, page: 1, size: 20 });
  api.getStudentVerification.mockResolvedValue(CARD);
  api.approveStudentVerification.mockResolvedValue({ ...ITEM, status: 'approved' });
  api.rejectStudentVerification.mockResolvedValue({ ...ITEM, status: 'rejected' });
});

async function openCard() {
  render(<StudentVerificationsPage />);
  fireEvent.click(await screen.findByRole('button', { name: /Открыть заявку: Иван Тестов/ }));
  return screen.findByRole('dialog', { name: 'Заявка на подтверждение студента' });
}

test('список: заявки «На проверке» по умолчанию, номера билета в списке нет', async () => {
  render(<StudentVerificationsPage />);
  expect(await screen.findByText('Иван Тестов')).toBeInTheDocument();
  expect(api.getStudentVerifications).toHaveBeenCalledWith(
    expect.objectContaining({ status: 'pending', page: 1 }),
  );
  expect(screen.queryByText('000123')).toBeNull();
  expect(screen.getByRole('button', { name: 'На проверке' }))
    .toHaveAttribute('aria-pressed', 'true');
});

test('фильтр статуса запрашивает список на сервере', async () => {
  render(<StudentVerificationsPage />);
  await screen.findByText('Иван Тестов');
  fireEvent.click(screen.getByRole('button', { name: 'Подтверждено' }));
  await waitFor(() => expect(api.getStudentVerifications).toHaveBeenLastCalledWith(
    expect.objectContaining({ status: 'approved', page: 1 }),
  ));
});

test('карточка показывает номер; «Подтвердить» шлёт решение и обновляет список', async () => {
  const dialog = await openCard();
  expect(await within(dialog).findByText('000123')).toBeInTheDocument();
  expect(api.getStudentVerification).toHaveBeenCalledWith(UUID);

  fireEvent.click(within(dialog).getByRole('button', { name: 'Подтвердить' }));
  await waitFor(() => expect(api.approveStudentVerification).toHaveBeenCalledWith(UUID));
  await waitFor(() => expect(api.getStudentVerifications).toHaveBeenCalledTimes(2));
});

test('отказ требует пояснения и отправляет его без пробелов по краям', async () => {
  const dialog = await openCard();
  await within(dialog).findByText('000123');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Отклонить' }));
  fireEvent.click(within(dialog).getByRole('button', { name: 'Отклонить заявку' }));
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Укажите пояснение отказа');
  expect(api.rejectStudentVerification).not.toHaveBeenCalled();

  fireEvent.change(within(dialog).getByLabelText(/Пояснение отказа/), {
    target: { value: '  Номер не совпадает  ' },
  });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Отклонить заявку' }));
  await waitFor(() => expect(api.rejectStudentVerification)
    .toHaveBeenCalledWith(UUID, 'Номер не совпадает'));
});

test('собственная заявка: кнопок решения нет, показано пояснение', async () => {
  api.getStudentVerification.mockResolvedValue({ ...CARD, can_review: false });
  const dialog = await openCard();
  expect(await within(dialog).findByText('Нельзя проверять собственную заявку.'))
    .toBeInTheDocument();
  expect(within(dialog).queryByRole('button', { name: 'Подтвердить' })).toBeNull();
  expect(within(dialog).queryByRole('button', { name: 'Отклонить' })).toBeNull();
});

test('отказ backend по коду показывает фиксированный текст', async () => {
  api.approveStudentVerification.mockRejectedValue(
    error('verification_already_decided', 'raw backend text'),
  );
  const dialog = await openCard();
  await within(dialog).findByText('000123');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Подтвердить' }));
  expect(await within(dialog).findByRole('alert'))
    .toHaveTextContent('По заявке уже принято другое решение.');
});

test('сбой аудита чтения (503): номер не показан, выводится сообщение', async () => {
  api.getStudentVerification.mockRejectedValue(
    error(undefined, 'Не удалось зафиксировать обращение к данным заявки. Повторите попытку.'),
  );
  const dialog = await openCard();
  expect(await within(dialog).findByRole('alert'))
    .toHaveTextContent('Не удалось зафиксировать обращение');
  expect(within(dialog).queryByText('000123')).toBeNull();
});

test('в режиме «под именем» раздел недоступен и запросов нет', async () => {
  useAuth.mockReturnValue({ isImpersonating: true });
  render(<StudentVerificationsPage />);
  expect(await screen.findByText(/недоступна при входе под именем/)).toBeInTheDocument();
  expect(api.getStudentVerifications).not.toHaveBeenCalled();
});
