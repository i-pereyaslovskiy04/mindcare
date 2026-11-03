import fs from 'fs';
import path from 'path';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import MeetingTypesPage from './MeetingTypesPage';
import * as api from '../../api/appointments.api';

jest.mock('../../api/appointments.api');

const TYPES = [
  { id: 1, name: 'Первичная консультация', description: '', duration_minutes: 180, buffer_minutes: 60,
    allow_in_person: true, allow_online: true, is_group: false, is_active: true, is_bookable: true, display_order: 0 },
  { id: 2, name: 'Групповое занятие', description: '', duration_minutes: 90, buffer_minutes: 0,
    allow_in_person: false, allow_online: true, is_group: true, is_active: false, is_bookable: false, display_order: 1 },
];

beforeEach(() => {
  jest.clearAllMocks();
  api.getMeetingTypes.mockResolvedValue({ items: TYPES });
  api.updateMeetingType.mockResolvedValue({});
});

const table = () => screen.getByRole('table', { name: 'Типы встреч' });
const list = () => screen.getByRole('list', { name: 'Типы встреч' });
const row = (name) => within(table()).getAllByRole('row').find((r) => within(r).queryByText(name, { selector: '.primary' }));
const record = (name) => within(list()).getAllByRole('listitem')
  .find((li) => within(li).queryByRole('heading', { level: 2, name }));

// Декоративной подписи роли над заголовком нет ни в одном кабинете
// (страница общая для /supervisor и /admin); содержательный h1 остаётся.
test('no decorative role label above the heading', async () => {
  api.getMeetingTypes.mockResolvedValue({ items: [] });
  render(<MeetingTypesPage />);
  await waitFor(() => expect(api.getMeetingTypes).toHaveBeenCalled());
  expect(screen.queryByText('Супервизор')).toBeNull();
  expect(screen.queryByText('Администратор')).toBeNull();
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Типы встреч');
});

test('wide: Тип встречи | Доступность | Параметры | Действия', async () => {
  render(<MeetingTypesPage />);
  await screen.findByRole('table', { name: 'Типы встреч' });
  await waitFor(() => expect(row('Первичная консультация')).toBeDefined());
  expect(within(table()).getAllByRole('columnheader').map((th) => th.textContent))
    .toEqual(['Тип встречи', 'Доступность', 'Параметры', 'Действия']);
  const r = row('Первичная консультация');
  expect(within(r).getByText('Активен')).toBeInTheDocument();
  expect(within(r).getByText('Запись открыта')).toBeInTheDocument();
  expect(within(r).getByText('180 мин + 60 мин буфер')).toBeInTheDocument();
  expect(within(r).getByText(/Онлайн и очно/)).toBeInTheDocument();
  expect(within(r).getByText('Индивидуальный')).toBeInTheDocument();
  const g = row('Групповое занятие');
  expect(within(g).getByText('Отключён')).toBeInTheDocument();
  expect(within(g).getByText('Запись закрыта')).toBeInTheDocument();
  expect(within(g).getByText('90 мин')).toBeInTheDocument();
  expect(within(g).getByText('Групповой')).toBeInTheDocument();
  expect(within(record('Групповое занятие')).getAllByRole('term').map((t) => t.textContent))
    .toEqual(['Длительность', 'Формат', 'Тип']);
});

test('«Изменить» открывает форму; «Отключить» / «Включить» в меню — PATCH is_active', async () => {
  render(<MeetingTypesPage />);
  await waitFor(() => expect(row('Первичная консультация')).toBeDefined());
  fireEvent.click(within(row('Первичная консультация')).getByRole('button', { name: 'Другие действия: Первичная консультация' }));
  expect(screen.getAllByRole('menuitem').map((i) => i.textContent)).toEqual(['Отключить']);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Отключить' }));
  await waitFor(() => expect(api.updateMeetingType).toHaveBeenCalledWith(1, { is_active: false }));

  fireEvent.click(within(record('Групповое занятие')).getByRole('button', { name: 'Другие действия: Групповое занятие' }));
  expect(screen.getAllByRole('menuitem').map((i) => i.textContent)).toEqual(['Включить']);

  fireEvent.click(within(record('Групповое занятие')).getByRole('button', { name: 'Изменить Групповое занятие' }));
  expect(await screen.findByRole('dialog', { name: 'Редактировать тип встречи' })).toBeInTheDocument();
});

test('ошибка — с «Повторить» снаружи таблицы; пусто — текст ResponsiveTable', async () => {
  api.getMeetingTypes.mockRejectedValueOnce(new Error('Сбой'));
  render(<MeetingTypesPage />);
  expect(await screen.findByText('Ошибка загрузки: Сбой')).toBeInTheDocument();
  expect(screen.queryByRole('table')).toBeNull();
  api.getMeetingTypes.mockResolvedValueOnce({ items: [] });
  fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
  await waitFor(() => expect(screen.getAllByText('Нет типов встреч. Создайте первый тип консультации.')).toHaveLength(2));
});

test('нет локальной табличной и responsive-механики', () => {
  const css = fs.readFileSync(path.join(__dirname, 'MeetingTypesPage.module.css'), 'utf8');
  expect(fs.readFileSync(path.join(__dirname, 'MeetingTypesPage.jsx'), 'utf8')).not.toMatch(/<table|<thead|<tr/);
  expect(css).not.toMatch(/@container|overflow-x|\.table/);
});
