import fs from 'fs';
import path from 'path';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import ServiceCardsPage from './ServiceCardsPage';
import * as api from '../../api/serviceCards.api';

jest.mock('../../api/serviceCards.api');

const CARDS = [
  { id: 1, title: 'Индивидуальное консультирование', description: '', link: '', image_url: '/media/card-1.jpg', is_active: true, display_order: 1 },
  { id: 3, title: 'Психодиагностика', description: '', link: '', image_url: null, is_active: false, display_order: 10 },
];

beforeEach(() => {
  jest.clearAllMocks();
  api.getSupervisorServiceCards.mockResolvedValue({ items: CARDS });
  api.updateServiceCard.mockResolvedValue({});
  api.deleteServiceCard.mockResolvedValue(null);
});

const table = () => screen.getByRole('table', { name: 'Карточки услуг' });
const list = () => screen.getByRole('list', { name: 'Карточки услуг' });
const row = (title) => within(table()).getAllByRole('row').find((r) => within(r).queryByText(title, { selector: '.primary' }));
const record = (title) => within(list()).getAllByRole('listitem')
  .find((li) => within(li).queryByRole('heading', { level: 2, name: title }));

async function renderPage() {
  render(<ServiceCardsPage />);
  await waitFor(() => expect(row('Психодиагностика')).toBeDefined());
}

test('wide: Карточка (картинка — identity.media) | Статус | Порядок | Действия', async () => {
  await renderPage();
  expect(within(table()).getAllByRole('columnheader').map((th) => th.textContent))
    .toEqual(['Карточка', 'Статус', 'Порядок', 'Действия']);
  const r = row('Индивидуальное консультирование');
  expect(within(r).getAllByRole('presentation')[0]).toHaveAttribute('src', '/media/card-1.jpg');
  expect(within(r).getByText('Активна')).toBeInTheDocument();
  expect(within(row('Психодиагностика')).getByText('Отключена')).toBeInTheDocument();
  expect(within(row('Психодиагностика')).getByText('10')).toBeInTheDocument();
  expect(within(record('Психодиагностика')).getByRole('term')).toHaveTextContent('Порядок');
});

test('«Изменить» — кнопкой; «Включить» и «Удалить» — в меню', async () => {
  await renderPage();
  fireEvent.click(within(record('Психодиагностика')).getByRole('button', { name: 'Другие действия: карточка «Психодиагностика»' }));
  expect(screen.getAllByRole('menuitem').map((i) => i.textContent)).toEqual(['Включить', 'Удалить']);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Включить' }));
  await waitFor(() => expect(api.updateServiceCard).toHaveBeenCalled());
  expect(api.updateServiceCard.mock.calls[0][0]).toBe(3);

  fireEvent.click(within(row('Индивидуальное консультирование')).getByRole('button', { name: 'Другие действия: карточка «Индивидуальное консультирование»' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Удалить' }));
  expect(screen.getByText('Удалить карточку?')).toBeInTheDocument();

  fireEvent.click(within(row('Психодиагностика')).getByRole('button', { name: 'Изменить карточку «Психодиагностика»' }));
  expect(await screen.findByRole('dialog', { name: 'Редактировать карточку' })).toBeInTheDocument();
});

test('ошибка — с «Повторить» снаружи таблицы; пусто — текст ResponsiveTable', async () => {
  api.getSupervisorServiceCards.mockRejectedValueOnce(new Error('Сбой'));
  render(<ServiceCardsPage />);
  expect(await screen.findByText('Ошибка загрузки: Сбой')).toBeInTheDocument();
  api.getSupervisorServiceCards.mockResolvedValueOnce({ items: [] });
  fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
  await waitFor(() => expect(screen.getAllByText('Нет карточек. На странице «Услуги» показывается стандартный набор.')).toHaveLength(2));
});

test('нет локальной табличной и responsive-механики', () => {
  expect(fs.readFileSync(path.join(__dirname, 'ServiceCardsPage.jsx'), 'utf8')).not.toMatch(/<table|<thead|<tr/);
  expect(fs.readFileSync(path.join(__dirname, 'ServiceCardsPage.module.css'), 'utf8'))
    .not.toMatch(/@container|overflow-x|\.table|\.thumb/);
});
