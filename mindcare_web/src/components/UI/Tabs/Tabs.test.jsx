import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import Tabs, { tabButtonId, tabPanelId } from './Tabs';

const TABS = [
  { id: 'a', label: 'Первая' },
  { id: 'b', label: 'Вторая' },
  { id: 'c', label: 'Третья' },
];

function setup(props = {}) {
  const onChange = jest.fn();
  render(<Tabs tabs={TABS} active="a" onChange={onChange} label="Разделы" idPrefix="demo" {...props} />);
  return onChange;
}

test('tablist с подписью, кнопки role=tab с id/aria-controls по префиксу', () => {
  setup();
  expect(screen.getByRole('tablist', { name: 'Разделы' })).toBeInTheDocument();
  TABS.forEach((tab) => {
    const button = screen.getByRole('tab', { name: tab.label });
    expect(button).toHaveAttribute('type', 'button');
    expect(button).toHaveAttribute('id', tabButtonId('demo', tab.id));
    expect(button).toHaveAttribute('aria-controls', tabPanelId('demo', tab.id));
  });
  expect(tabButtonId('demo', 'a')).toBe('demo-tab-a');
  expect(tabPanelId('demo', 'a')).toBe('demo-panel-a');
});

test('aria-selected и roving tabIndex только у активной вкладки', () => {
  setup({ active: 'b' });
  expect(screen.getByRole('tab', { name: 'Вторая' })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByRole('tab', { name: 'Вторая' })).toHaveAttribute('tabindex', '0');
  expect(screen.getByRole('tab', { name: 'Первая' })).toHaveAttribute('tabindex', '-1');
  expect(screen.getByRole('tab', { name: 'Первая' })).toHaveAttribute('aria-selected', 'false');
});

test('клик переключает вкладку', () => {
  const onChange = setup();
  fireEvent.click(screen.getByRole('tab', { name: 'Третья' }));
  expect(onChange).toHaveBeenCalledWith('c');
});

test.each([
  ['ArrowRight', 'a', 'b'],
  ['ArrowRight', 'c', 'a'],
  ['ArrowLeft', 'a', 'c'],
  ['Home', 'c', 'a'],
  ['End', 'a', 'c'],
])('клавиша %s на вкладке %s активирует %s и переносит фокус', async (key, from, to) => {
  const onChange = setup({ active: from });
  fireEvent.keyDown(screen.getByRole('tablist'), { key });
  expect(onChange).toHaveBeenCalledWith(to);
  const label = TABS.find((tab) => tab.id === to).label;
  await waitFor(() => expect(screen.getByRole('tab', { name: label })).toHaveFocus());
});

test('прочие клавиши ничего не делают', () => {
  const onChange = setup();
  fireEvent.keyDown(screen.getByRole('tablist'), { key: 'Tab' });
  expect(onChange).not.toHaveBeenCalled();
});

describe('indicator', () => {
  it('по умолчанию — прежний вид (underline): модификатора нет', () => {
    setup();
    expect(screen.getByRole('tablist').className).not.toMatch(/indicatorFill/);
  });

  it('indicator="fill" добавляет модификатор без подчёркивания и не трогает остальной вид', () => {
    setup({ indicator: 'fill', fill: true });
    const list = screen.getByRole('tablist');
    expect(list.className).toMatch(/indicatorFill/);
    expect(list.className).toMatch(/fill/);
  });

  it('indicator="fill": aria-selected, roving tabIndex и клавиши работают как раньше', () => {
    const onChange = setup({ indicator: 'fill', active: 'b' });
    expect(screen.getByRole('tab', { name: 'Вторая' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Вторая' })).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tab', { name: 'Первая' })).toHaveAttribute('tabindex', '-1');
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith('c');
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'Home' });
    expect(onChange).toHaveBeenCalledWith('a');
  });
});
