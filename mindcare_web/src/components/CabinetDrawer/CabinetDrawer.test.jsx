import { useRef, useState } from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import CabinetDrawer from './CabinetDrawer';

/** Мини-обвязка как в layout'ах: hamburger + drawer с навигацией. */
function Harness() {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  return (
    <>
      <button ref={triggerRef} type="button" onClick={() => setOpen(true)}>Открыть меню</button>
      <a href="/page">Ссылка страницы</a>
      <CabinetDrawer open={open} onClose={() => setOpen(false)} returnFocusRef={triggerRef} id="d1">
        <a href="/home">Бренд</a>
        <nav>
          <a href="/a">Пункт А</a>
          <a href="/b">Пункт Б</a>
        </nav>
      </CabinetDrawer>
    </>
  );
}

const openDrawer = () => {
  const trigger = screen.getByRole('button', { name: 'Открыть меню' });
  trigger.focus();
  fireEvent.click(trigger);
  return { trigger, drawer: screen.getByRole('dialog', { name: 'Меню кабинета' }) };
};

test('закрытый drawer не рендерится', () => {
  render(<Harness />);
  expect(screen.queryByRole('dialog')).toBeNull();
});

test('открытие: aria-modal dialog, фокус на «Закрыть меню»', () => {
  render(<Harness />);
  const { trigger, drawer } = openDrawer();
  expect(drawer).toHaveAttribute('aria-modal', 'true');
  expect(drawer).toHaveAttribute('id', 'd1');
  expect(within(drawer).getByRole('button', { name: 'Закрыть меню' })).toHaveFocus();
  expect(trigger).not.toHaveFocus();
});

test('Tab / Shift+Tab ходят по кругу внутри drawer', () => {
  render(<Harness />);
  const { drawer } = openDrawer();
  const close = within(drawer).getByRole('button', { name: 'Закрыть меню' });
  const last = within(drawer).getByRole('link', { name: 'Пункт Б' });

  fireEvent.keyDown(close, { key: 'Tab', shiftKey: true });
  expect(last).toHaveFocus();

  fireEvent.keyDown(last, { key: 'Tab' });
  expect(close).toHaveFocus();
});

test('Escape закрывает и возвращает фокус на hamburger', () => {
  render(<Harness />);
  const { trigger } = openDrawer();
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(trigger).toHaveFocus();
});

test('«Закрыть меню» закрывает и возвращает фокус на hamburger', () => {
  render(<Harness />);
  const { trigger } = openDrawer();
  fireEvent.click(screen.getByRole('button', { name: 'Закрыть меню' }));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(trigger).toHaveFocus();
});

test('клик по backdrop закрывает drawer', () => {
  const onClose = jest.fn();
  const { container } = render(
    <CabinetDrawer open onClose={onClose}>
      <p>меню</p>
    </CabinetDrawer>,
  );
  // Backdrop декоративный (aria-hidden), ролей у него нет — берём первый узел.
  // eslint-disable-next-line testing-library/no-node-access, testing-library/no-container
  fireEvent.click(container.firstChild);
  expect(onClose).toHaveBeenCalledTimes(1);
});

describe('изоляция фона', () => {
  /** Как в layout'ах: drawer — сосед sidebar и main внутри оболочки. */
  function Shell() {
    const [open, setOpen] = useState(false);
    const triggerRef = useRef(null);
    return (
      <div data-testid="shell">
        <aside data-testid="sidebar"><a href="/x">Пункт sidebar</a></aside>
        <main data-testid="main">
          <button ref={triggerRef} type="button" onClick={() => setOpen(true)}>Открыть меню</button>
        </main>
        <section data-testid="already-inert" inert>старое</section>
        <CabinetDrawer open={open} onClose={() => setOpen(false)} returnFocusRef={triggerRef}>
          <a href="/a">Пункт А</a>
        </CabinetDrawer>
      </div>
    );
  }

  test('открыт: sidebar и main — inert, сам drawer и оболочка — нет', () => {
    render(<Shell />);
    fireEvent.click(screen.getByRole('button', { name: 'Открыть меню' }));

    expect(screen.getByTestId('sidebar')).toHaveAttribute('inert');
    expect(screen.getByTestId('main')).toHaveAttribute('inert');
    expect(screen.getByTestId('shell')).not.toHaveAttribute('inert');
    expect(screen.getByTestId('shell')).not.toHaveAttribute('aria-hidden');
    const drawer = screen.getByRole('dialog', { name: 'Меню кабинета' });
    expect(drawer).not.toHaveAttribute('inert');
    expect(within(drawer).getByRole('link', { name: 'Пункт А' })).toBeInTheDocument();
  });

  test('закрытие снимает inert и возвращает фокус на hamburger', () => {
    render(<Shell />);
    const trigger = screen.getByRole('button', { name: 'Открыть меню' });
    trigger.focus();
    fireEvent.click(trigger);
    fireEvent.keyDown(window, { key: 'Escape' });

    expect(screen.getByTestId('sidebar')).not.toHaveAttribute('inert');
    expect(screen.getByTestId('main')).not.toHaveAttribute('inert');
    expect(trigger).toHaveFocus();
  });

  test('чужой inert drawer не снимает', () => {
    render(<Shell />);
    fireEvent.click(screen.getByRole('button', { name: 'Открыть меню' }));
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть меню' }));
    expect(screen.getByTestId('already-inert')).toHaveAttribute('inert');
  });
});
