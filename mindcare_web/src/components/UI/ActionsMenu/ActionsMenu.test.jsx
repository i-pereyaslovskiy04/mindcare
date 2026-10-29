import { fireEvent, render, screen } from '@testing-library/react';
import ActionsMenu from './ActionsMenu';

function setup(overrides = {}) {
  const handlers = { a: jest.fn(), b: jest.fn(), c: jest.fn() };
  const items = overrides.items || [
    { id: 'a', label: 'Первое', onSelect: handlers.a },
    { id: 'b', label: 'Недоступное', onSelect: handlers.b, disabled: true },
    { id: 'c', label: 'Опасное', onSelect: handlers.c, tone: 'danger' },
  ];
  render(
    <>
      <ActionsMenu triggerLabel="Другие действия: Ли Ан" items={items} />
      <button type="button">После меню</button>
    </>,
  );
  return handlers;
}

const trigger = () => screen.getByRole('button', { name: 'Другие действия: Ли Ан' });

test('кнопка с понятным именем; меню закрыто, пока не нажата', () => {
  setup();
  expect(trigger()).toHaveAttribute('aria-haspopup', 'menu');
  expect(trigger()).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByRole('menu')).toBeNull();
});

test('открытие: фокус на первом доступном пункте; выбор вызывает onSelect и закрывает меню', () => {
  const h = setup();
  fireEvent.click(trigger());
  expect(trigger()).toHaveAttribute('aria-expanded', 'true');
  const menu = screen.getByRole('menu', { name: 'Другие действия: Ли Ан' });
  expect(menu).toBeInTheDocument();
  expect(screen.getByRole('menuitem', { name: 'Первое' })).toHaveFocus();

  fireEvent.click(screen.getByRole('menuitem', { name: 'Опасное' }));
  expect(h.c).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('menu')).toBeNull();
  expect(trigger()).toHaveFocus();
});

test('недоступный пункт не вызывает действие и пропускается стрелками', () => {
  const h = setup();
  fireEvent.click(trigger());
  const disabled = screen.getByRole('menuitem', { name: 'Недоступное' });
  expect(disabled).toBeDisabled();
  fireEvent.click(disabled);
  expect(h.b).not.toHaveBeenCalled();

  fireEvent.keyDown(screen.getByRole('menu'), { key: 'ArrowDown' });
  expect(screen.getByRole('menuitem', { name: 'Опасное' })).toHaveFocus();
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'ArrowDown' });   // по кругу
  expect(screen.getByRole('menuitem', { name: 'Первое' })).toHaveFocus();
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'End' });
  expect(screen.getByRole('menuitem', { name: 'Опасное' })).toHaveFocus();
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'Home' });
  expect(screen.getByRole('menuitem', { name: 'Первое' })).toHaveFocus();
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'ArrowUp' });
  expect(screen.getByRole('menuitem', { name: 'Опасное' })).toHaveFocus();
});

test('ArrowDown на кнопке открывает меню', () => {
  setup();
  fireEvent.keyDown(trigger(), { key: 'ArrowDown' });
  expect(screen.getByRole('menu')).toBeInTheDocument();
  expect(screen.getByRole('menuitem', { name: 'Первое' })).toHaveFocus();
});

test('Escape закрывает меню и возвращает фокус на кнопку, не всплывая дальше', () => {
  setup();
  const outer = jest.fn();
  document.addEventListener('keydown', outer);
  fireEvent.click(trigger());
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' });
  expect(screen.queryByRole('menu')).toBeNull();
  expect(trigger()).toHaveFocus();
  expect(outer).not.toHaveBeenCalled();
  document.removeEventListener('keydown', outer);
});

test('Tab закрывает меню и возвращает фокус в порядок страницы с кнопки', () => {
  setup();
  fireEvent.click(trigger());
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'Tab' });
  expect(screen.queryByRole('menu')).toBeNull();
  expect(trigger()).toHaveFocus();
});

test('клик вне меню закрывает его', () => {
  setup();
  fireEvent.click(trigger());
  fireEvent.mouseDown(screen.getByRole('button', { name: 'После меню' }));
  expect(screen.queryByRole('menu')).toBeNull();
});

test('меню — в portal (document.body), не внутри контейнера кнопки', () => {
  setup();
  fireEvent.click(trigger());
  expect(screen.getByRole('menu').parentElement).toBe(document.body); // eslint-disable-line testing-library/no-node-access
});

test('пустой список — ничего не рендерится', () => {
  setup({ items: [] });
  expect(screen.queryByRole('button', { name: /Другие действия/ })).toBeNull();
});
