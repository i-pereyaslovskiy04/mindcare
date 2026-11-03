import fs from 'fs';
import path from 'path';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

test('Enter и Space на вкладке активируют её (нативная кнопка)', () => {
  const onChange = setup();
  const second = screen.getByRole('tab', { name: 'Вторая' });
  second.focus();
  userEvent.type(second, '{enter}', { skipClick: true });
  expect(onChange).toHaveBeenLastCalledWith('b');
  const third = screen.getByRole('tab', { name: 'Третья' });
  third.focus();
  userEvent.type(third, '{space}', { skipClick: true });
  expect(onChange).toHaveBeenLastCalledWith('c');
});

test('неизвестная активная вкладка: стрелки ничего не делают', () => {
  const onChange = setup({ active: 'missing' });
  fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' });
  expect(onChange).not.toHaveBeenCalled();
});

describe('один вид для всех страниц', () => {
  it('нет вариантов вида: проп indicator не поддерживается, модификатора нет', () => {
    setup({ indicator: 'underline' });
    const list = screen.getByRole('tablist');
    expect(list.className).not.toMatch(/indicator/i);
    expect(list).not.toHaveAttribute('indicator');
  });

  it('fill — универсальный модификатор раскладки (равные колонки)', () => {
    setup({ fill: true, className: 'pageTabs' });
    const list = screen.getByRole('tablist');
    expect(list.className).toMatch(/fill/);
    expect(list.className).toMatch(/pageTabs/);
  });
});

describe('Tabs.module.css', () => {
  const css = fs.readFileSync(path.join(__dirname, 'Tabs.module.css'), 'utf8');
  const block = (selector) => {
    const start = css.indexOf(`${selector} {`);
    expect(start).toBeGreaterThanOrEqual(0);
    return css.slice(start, css.indexOf('}', start));
  };

  test('выбранная — поверхность, рамка --outline, тень и жирный шрифт, без акцентной заливки', () => {
    const active = block('.tabActive,\n.tabActive:hover');
    expect(active).toMatch(/background:\s*var\(--surface\);/);
    expect(active).toMatch(/color:\s*var\(--on-surface\);/);
    expect(active).toMatch(/border-color:\s*var\(--outline\)/);
    expect(active).toMatch(/box-shadow:/);
    expect(active).toMatch(/font-weight:\s*700/);
    expect(css).not.toMatch(/--primary/);
    expect(css).not.toMatch(/::after/);
    expect(css).not.toMatch(/indicator/i);
    // Рамка есть у всех вкладок — размеры при переключении не скачут.
    expect(block('.tab')).toMatch(/border:\s*1px solid transparent/);
  });

  test('своих внешних отступов нет; по умолчанию ширина по содержимому', () => {
    const list = block('.tabs');
    expect(list).not.toMatch(/margin/);
    expect(list).toMatch(/width:\s*fit-content/);
    expect(block('.fill .tab')).toMatch(/flex:\s*1 1 0/);
  });

  test('узкий экран — равные колонки на всю ширину', () => {
    const narrow = css.slice(css.indexOf('@media (max-width: 480px)'));
    expect(narrow).toMatch(/\.tab\s*\{[^}]*flex:\s*1 1 0/);
    expect(narrow).toMatch(/\.tabs\s*\{[^}]*width:\s*auto/);
  });

  test('focus ring и режим для слабовидящих', () => {
    expect(block('.tab:focus-visible')).toMatch(/outline:\s*var\(--focus-ring-width\)/);
    expect(block(":root[data-a11y='on'] .tabActive")).toMatch(/background:\s*var\(--a11y-fg\)/);
  });
});
