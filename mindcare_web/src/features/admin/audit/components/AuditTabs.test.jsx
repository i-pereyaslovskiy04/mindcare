import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AuditTabs, { tabButtonId, tabPanelId } from './AuditTabs';

const TABS = [
  { id: 'audit_log', label: 'Действия' },
  { id: 'auth_log', label: 'Входы и безопасность' },
  { id: 'data_change_log', label: 'Изменённые поля' },
];

function setup(active = 'audit_log') {
  const onChange = jest.fn();
  render(<AuditTabs tabs={TABS} active={active} onChange={onChange} />);
  return onChange;
}

describe('семантика вкладок', () => {
  test('контейнер — tablist, элементы — нативные button с role="tab"', () => {
    setup();
    const tablist = screen.getByRole('tablist');
    expect(tablist).toBeInTheDocument();

    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(3);
    tabs.forEach((tab) => {
      expect(tab.tagName).toBe('BUTTON');
      expect(tab).toHaveAttribute('type', 'button');
    });
  });

  test('aria-selected отмечает ровно одну вкладку', () => {
    setup('auth_log');
    expect(screen.getByRole('tab', { name: 'Действия' }))
      .toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('tab', { name: 'Входы и безопасность' }))
      .toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Изменённые поля' }))
      .toHaveAttribute('aria-selected', 'false');
  });

  test('каждая вкладка связана со своей панелью', () => {
    setup();
    TABS.forEach((tab) => {
      const button = screen.getByRole('tab', { name: tab.label });
      expect(button).toHaveAttribute('id', tabButtonId(tab.id));
      expect(button).toHaveAttribute('aria-controls', tabPanelId(tab.id));
    });
  });

  test('в Tab-обходе участвует только активная вкладка (roving tabIndex)', () => {
    setup('audit_log');
    expect(screen.getByRole('tab', { name: 'Действия' })).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tab', { name: 'Изменённые поля' }))
      .toHaveAttribute('tabindex', '-1');
  });
});

describe('переключение', () => {
  test('клик выбирает вкладку', () => {
    const onChange = setup();
    fireEvent.click(screen.getByRole('tab', { name: 'Изменённые поля' }));
    expect(onChange).toHaveBeenCalledWith('data_change_log');
  });

  test('ArrowRight переходит к следующей и переносит фокус', async () => {
    const onChange = setup('audit_log');
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith('auth_log');
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Входы и безопасность' })).toHaveFocus();
    });
  });

  test('ArrowLeft переходит к предыдущей', () => {
    const onChange = setup('auth_log');
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowLeft' });
    expect(onChange).toHaveBeenCalledWith('audit_log');
  });

  test('стрелки заворачиваются по кругу', () => {
    const onChange = setup('data_change_log');
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith('audit_log');
  });

  test('Home и End прыгают на края', () => {
    const onChange = setup('auth_log');
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'Home' });
    expect(onChange).toHaveBeenCalledWith('audit_log');

    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'End' });
    expect(onChange).toHaveBeenCalledWith('data_change_log');
  });

  test('посторонняя клавиша ничего не переключает', () => {
    const onChange = setup();
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'a' });
    expect(onChange).not.toHaveBeenCalled();
  });
});
