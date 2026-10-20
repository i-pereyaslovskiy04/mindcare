import { useState } from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import Modal from './Modal';

/** Триггер + модалка, как у потребителей shared Modal. */
function Harness({ initialOpen = false }) {
  const [open, setOpen] = useState(initialOpen);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Открыть</button>
      <Modal open={open} onClose={() => setOpen(false)} ariaLabel="Тестовый диалог">
        <label htmlFor="m-name">Имя</label>
        <input id="m-name" />
        <button type="button">Сохранить</button>
      </Modal>
    </>
  );
}

/** Overlay модалки — ближайший предок dialog'а (портал в body). */
// eslint-disable-next-line testing-library/no-node-access
const overlayOf = (dialog) => dialog.parentElement;

describe('Modal — закрытая', () => {
  test('нет активного dialog, контролы вне дерева доступности, overlay inert', () => {
    render(<Harness />);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Закрыть' })).toBeNull();
    expect(screen.queryByRole('textbox', { name: 'Имя' })).toBeNull();

    // Модалка смонтирована (анимация, состояние), но изолирована целиком:
    // inert — ни фокуса, ни кликов; одного aria-hidden недостаточно.
    const dialog = screen.getByRole('dialog', { hidden: true });
    expect(overlayOf(dialog)).toHaveAttribute('inert');
    expect(overlayOf(dialog)).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('Modal — открытая', () => {
  test('dialog с именем, overlay не inert, фокус на первом контроле', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Открыть' }));

    const dialog = screen.getByRole('dialog', { name: 'Тестовый диалог' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(overlayOf(dialog)).not.toHaveAttribute('inert');
    await waitFor(() =>
      expect(within(dialog).getByRole('button', { name: 'Закрыть' })).toHaveFocus(),
    );
  });

  test('Tab / Shift+Tab не выходят за пределы dialog', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Открыть' }));
    const dialog = screen.getByRole('dialog', { name: 'Тестовый диалог' });
    const first = within(dialog).getByRole('button', { name: 'Закрыть' });
    const last = within(dialog).getByRole('button', { name: 'Сохранить' });
    await waitFor(() => expect(first).toHaveFocus());

    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(last).toHaveFocus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(first).toHaveFocus();
  });

  test('Escape закрывает, фокус возвращается на триггер, overlay снова inert', async () => {
    render(<Harness />);
    const trigger = screen.getByRole('button', { name: 'Открыть' });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Тестовый диалог' });
    await waitFor(() =>
      expect(within(dialog).getByRole('button', { name: 'Закрыть' })).toHaveFocus(),
    );

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(trigger).toHaveFocus();
    expect(overlayOf(screen.getByRole('dialog', { hidden: true }))).toHaveAttribute('inert');
  });

  test('крестик «Закрыть» закрывает', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Открыть' }));
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
