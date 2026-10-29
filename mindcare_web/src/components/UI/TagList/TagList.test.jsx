import fs from 'fs';
import path from 'path';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TagList from './TagList';

const mk = (...labels) => labels.map((label) => ({ key: label, label }));
const TOPICS = mk('Стресс', 'Тревожность', 'Сон', 'Сессия', 'Семья');

const topics = () => screen.getByRole('list', { name: 'Темы' });
const visibleLabels = () => within(topics()).getAllByRole('listitem').map((li) => li.textContent);

test('пустой набор — ничего не рендерит', () => {
  const { container } = render(<TagList items={[]} maxVisible={2} label="Темы" />);
  expect(container).toBeEmptyDOMElement();
});

test('без maxVisible или не больше лимита — все метки, без кнопки «+N»', () => {
  const { rerender } = render(<TagList items={TOPICS} label="Темы" />);
  expect(visibleLabels()).toEqual(['Стресс', 'Тревожность', 'Сон', 'Сессия', 'Семья']);
  expect(screen.queryByRole('button')).toBeNull();

  rerender(<TagList items={TOPICS.slice(0, 2)} maxVisible={2} label="Темы" />);
  expect(visibleLabels()).toEqual(['Стресс', 'Тревожность']);
  expect(screen.queryByRole('button')).toBeNull();
});

test('больше лимита — первые maxVisible и кнопка «+N» с доступным именем', () => {
  render(<TagList items={TOPICS} maxVisible={2} label="Темы" />);
  expect(visibleLabels()).toEqual(['Стресс', 'Тревожность']);
  const more = screen.getByRole('button', { name: '+3: показать все, всего 5' });
  expect(more).toHaveTextContent(/^\+3/);
  expect(more).toHaveAttribute('aria-expanded', 'false');
  expect(more).toHaveAttribute('aria-controls', topics().id);
});

test('«+N» раскрывает полный список и сворачивает его обратно (мышь)', () => {
  render(<TagList items={TOPICS} maxVisible={2} label="Темы" />);
  userEvent.click(screen.getByRole('button', { name: /^\+3/ }));
  expect(visibleLabels()).toHaveLength(5);
  const collapse = screen.getByRole('button', { name: 'Свернуть' });
  expect(collapse).toHaveAttribute('aria-expanded', 'true');

  userEvent.click(collapse);
  expect(visibleLabels()).toEqual(['Стресс', 'Тревожность']);
  expect(screen.getByRole('button', { name: /^\+3/ })).toHaveAttribute('aria-expanded', 'false');
});

test('клавиатура: кнопка в порядке Tab, Enter и Space переключают, фокус остаётся на ней', () => {
  render(<TagList items={TOPICS} maxVisible={2} label="Темы" />);
  userEvent.tab();
  const toggle = screen.getByRole('button', { name: /^\+3/ });
  expect(toggle).toHaveFocus();

  userEvent.keyboard('{Enter}');
  expect(visibleLabels()).toHaveLength(5);
  expect(screen.getByRole('button', { name: 'Свернуть' })).toHaveFocus();

  userEvent.keyboard(' ');
  expect(visibleLabels()).toHaveLength(2);
  expect(screen.getByRole('button', { name: /^\+3/ })).toHaveFocus();
});

test('длинная метка выводится полностью (не обрезается текстом)', () => {
  const long = 'Психологическая поддержка студентов в период адаптации к дистанционному обучению и сессии';
  render(<TagList items={mk(long)} maxVisible={2} label="Темы" />);
  expect(within(topics()).getByText(long)).toBeInTheDocument();
});

test('метки — shared Tag выбранного варианта', () => {
  render(<TagList items={mk('Стресс')} variant="category" label="Темы" />);
  expect(within(topics()).getByText('Стресс')).toHaveClass('tag', 'category');
});

test('shared-слой не зависит от фич', () => {
  ['TagList.jsx', 'TagList.module.css'].forEach((file) => {
    const src = fs.readFileSync(path.join(__dirname, file), 'utf8');
    expect(src).not.toMatch(/features\//);
    expect(src).not.toMatch(/news|api\//i);
  });
});
