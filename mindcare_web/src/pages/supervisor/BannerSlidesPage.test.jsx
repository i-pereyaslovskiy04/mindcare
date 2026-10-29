import fs from 'fs';
import path from 'path';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import BannerSlidesPage from './BannerSlidesPage';
import * as api from '../../api/bannerSlides.api';

jest.mock('../../api/bannerSlides.api');

const SLIDES = [
  { id: 1, label: '', title: 'Психологическая служба', highlight: 'Запишитесь онлайн', placement: 'home',
    display_order: 1, is_active: true, image_url: '/media/slide-1.jpg', button_text: '', button_link: '' },
  { id: 2, label: '', title: 'О центре', highlight: '', placement: 'about',
    display_order: 2, is_active: false, image_url: null, button_text: '', button_link: '' },
];

beforeEach(() => {
  jest.clearAllMocks();
  api.getSupervisorBannerSlides.mockResolvedValue({ items: SLIDES });
  api.updateBannerSlide.mockResolvedValue({});
  api.deleteBannerSlide.mockResolvedValue(null);
});

const table = () => screen.getByRole('table', { name: 'Слайды баннера' });
const list = () => screen.getByRole('list', { name: 'Слайды баннера' });
const row = (title) => within(table()).getAllByRole('row').find((r) => within(r).queryByText(title, { selector: '.primary' }));
const record = (title) => within(list()).getAllByRole('listitem')
  .find((li) => within(li).queryByRole('heading', { level: 2, name: title }));

async function renderPage() {
  render(<BannerSlidesPage />);
  await waitFor(() => expect(row('О центре')).toBeDefined());
}

test('wide: Слайд (картинка — identity.media) | Статус | Страница и порядок | Действия', async () => {
  await renderPage();
  expect(within(table()).getAllByRole('columnheader').map((th) => th.textContent))
    .toEqual(['Слайд', 'Статус', 'Страница и порядок', 'Действия']);
  const r = row('Психологическая служба');
  expect(within(r).getAllByRole('presentation')[0]).toHaveAttribute('src', '/media/slide-1.jpg');
  expect(within(r).getByText('Запишитесь онлайн')).toBeInTheDocument();
  expect(within(r).getByText('Активен')).toBeInTheDocument();
  expect(within(r).getByText('Главная', { exact: false })).toBeInTheDocument();
  expect(within(r).getByText('порядок 1')).toBeInTheDocument();
  expect(within(row('О центре')).queryAllByRole('presentation')).toHaveLength(0);
  expect(within(row('О центре')).getByText('Отключён')).toBeInTheDocument();
  expect(within(record('О центре')).getAllByRole('term').map((t) => t.textContent)).toEqual(['Страница', 'Порядок']);
});

test('«Изменить» — кнопкой; «Отключить»/«Включить» и «Удалить» — в меню', async () => {
  await renderPage();
  fireEvent.click(within(row('Психологическая служба')).getByRole('button', { name: 'Другие действия: слайд «Психологическая служба»' }));
  expect(screen.getAllByRole('menuitem').map((i) => i.textContent)).toEqual(['Отключить', 'Удалить']);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Отключить' }));
  await waitFor(() => expect(api.updateBannerSlide).toHaveBeenCalled());
  expect(api.updateBannerSlide.mock.calls[0][0]).toBe(1);

  fireEvent.click(within(record('О центре')).getByRole('button', { name: 'Другие действия: слайд «О центре»' }));
  expect(screen.getAllByRole('menuitem').map((i) => i.textContent)).toEqual(['Включить', 'Удалить']);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Удалить' }));
  expect(screen.getByText('Удалить слайд?')).toBeInTheDocument();
  expect(api.deleteBannerSlide).not.toHaveBeenCalled();

  fireEvent.click(within(row('О центре')).getByRole('button', { name: 'Изменить слайд «О центре»' }));
  expect(await screen.findByRole('dialog', { name: 'Редактировать слайд' })).toBeInTheDocument();
});

test('ошибка — с «Повторить» снаружи таблицы', async () => {
  api.getSupervisorBannerSlides.mockRejectedValueOnce(new Error('Сбой'));
  render(<BannerSlidesPage />);
  expect(await screen.findByText('Ошибка загрузки: Сбой')).toBeInTheDocument();
  expect(screen.queryByRole('table')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
  await waitFor(() => expect(row('О центре')).toBeDefined());
});

test('нет локальной табличной и responsive-механики', () => {
  expect(fs.readFileSync(path.join(__dirname, 'BannerSlidesPage.jsx'), 'utf8')).not.toMatch(/<table|<thead|<tr/);
  expect(fs.readFileSync(path.join(__dirname, 'BannerSlidesPage.module.css'), 'utf8'))
    .not.toMatch(/@container|overflow-x|\.table|\.thumb/);
});
