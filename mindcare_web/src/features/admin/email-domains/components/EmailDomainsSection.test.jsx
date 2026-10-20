import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import EmailDomainsSection from './EmailDomainsSection';
import * as api from '../../../../api/domains.api';

jest.mock('../../../../api/domains.api');

beforeEach(() => {
  api.getEmailDomains.mockResolvedValue([
    { id: 1, domain: 'donnu.ru', is_active: true, comment: null },
    { id: 2, domain: 'old.ru', is_active: false, comment: 'legacy' },
  ]);
  api.createEmailDomain.mockResolvedValue({
    id: 3, domain: 'new.ru', is_active: true, comment: null,
  });
  api.updateEmailDomain.mockResolvedValue({});
});

test('renders active and disabled domains with correct actions', async () => {
  render(<EmailDomainsSection />);

  expect(await screen.findByText('donnu.ru')).toBeInTheDocument();
  expect(screen.getByText('old.ru')).toBeInTheDocument();
  expect(screen.getByText('активен')).toBeInTheDocument();
  expect(screen.getByText('отключён')).toBeInTheDocument();
  // активный домен → «Отключить»; отключённый → «Включить»
  expect(screen.getByRole('button', { name: 'Отключить' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Включить' })).toBeInTheDocument();
});

test('add domain calls createEmailDomain with trimmed values', async () => {
  render(<EmailDomainsSection />);
  expect(await screen.findByText('donnu.ru')).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('Домен'), {
    target: { value: '  new.ru  ' },
  });
  fireEvent.change(screen.getByLabelText('Комментарий'), {
    target: { value: '  партнёр  ' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Добавить' }));

  await waitFor(() => expect(api.createEmailDomain).toHaveBeenCalledTimes(1));
  expect(api.createEmailDomain).toHaveBeenCalledWith({
    domain: 'new.ru',
    comment: 'партнёр',
  });
});

test('empty domain add shows inline error, no request', async () => {
  render(<EmailDomainsSection />);
  expect(await screen.findByText('donnu.ru')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Добавить' }));

  expect(await screen.findByText('Введите домен.')).toBeInTheDocument();
  expect(api.createEmailDomain).not.toHaveBeenCalled();
});

test('reactivate calls updateEmailDomain with is_active true', async () => {
  render(<EmailDomainsSection />);
  expect(await screen.findByText('old.ru')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Включить' }));

  await waitFor(() => expect(api.updateEmailDomain).toHaveBeenCalledTimes(1));
  expect(api.updateEmailDomain).toHaveBeenCalledWith(2, { is_active: true });
});

test('shows backend error on failed add (e.g. 409 duplicate)', async () => {
  const err = new Error('Домен уже есть в списке.');
  err.status = 409;
  api.createEmailDomain.mockRejectedValueOnce(err);

  render(<EmailDomainsSection />);
  expect(await screen.findByText('donnu.ru')).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('Домен'), {
    target: { value: 'donnu.ru' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Добавить' }));

  expect(await screen.findByText('Домен уже есть в списке.')).toBeInTheDocument();
});

test('disable opens a confirm dialog, and confirming calls updateEmailDomain(id, {is_active:false})', async () => {
  render(<EmailDomainsSection />);
  expect(await screen.findByText('donnu.ru')).toBeInTheDocument();

  // Отключить открывает confirm-диалог, но НЕ вызывает API сразу.
  fireEvent.click(screen.getByRole('button', { name: 'Отключить' }));
  expect(
    await screen.findByRole('heading', { name: 'Отключить домен?' }),
  ).toBeInTheDocument();
  expect(api.updateEmailDomain).not.toHaveBeenCalled();

  // Подтверждение внутри модалки вызывает API с ожидаемым payload.
  const dialog = screen.getByRole('dialog');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Отключить' }));

  await waitFor(() => expect(api.updateEmailDomain).toHaveBeenCalledTimes(1));
  expect(api.updateEmailDomain).toHaveBeenCalledWith(1, { is_active: false });
});

test('backend 409 on disable stays visible inside the modal as exactly one alert', async () => {
  const err = new Error('Нельзя отключить последний активный домен.');
  err.status = 409;
  api.updateEmailDomain.mockRejectedValueOnce(err);

  render(<EmailDomainsSection />);
  expect(await screen.findByText('donnu.ru')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Отключить' }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Отключить' }));

  const alerts = await screen.findAllByRole('alert');
  const matching = alerts.filter(
    (el) => el.textContent === 'Нельзя отключить последний активный домен.',
  );
  expect(matching).toHaveLength(1);
  expect(within(dialog).getByRole('alert')).toHaveTextContent(
    'Нельзя отключить последний активный домен.',
  );

  // Закрытие модалки (Отмена) очищает ошибку — не остаётся снаружи.
  fireEvent.click(within(dialog).getByRole('button', { name: 'Отмена' }));
  await waitFor(() =>
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
  );
  expect(
    screen.queryByText('Нельзя отключить последний активный домен.'),
  ).not.toBeInTheDocument();
});
