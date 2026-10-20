import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import AuditActorPicker from './AuditActorPicker';
import { getUsers } from '../../../../api/users.api';

jest.mock('../../../../api/users.api');

const RAW_USERS = [
  {
    id: 17,
    uuid: '11111111-1111-4111-8111-111111111111',
    full_name: 'Тестовый Пользователь',
    email: 'testovyy@example.test',
    deleted_at: null,
  },
  {
    id: 18,
    uuid: '22222222-2222-4222-8222-222222222222',
    full_name: 'Удалённый Аккаунт',
    email: 'deleted@example.test',
    deleted_at: '2026-01-01T00:00:00Z',
  },
];

const SELECTED = {
  uuid: RAW_USERS[0].uuid,
  fullName: 'Тестовый Пользователь',
  emailMasked: 't***@example.test',
  isDeleted: false,
};

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
  getUsers.mockResolvedValue({ items: RAW_USERS, total: 2 });
});

afterEach(() => {
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
});

function setup(props = {}) {
  const onSelect = jest.fn();
  const onClear = jest.fn();
  const view = render(
    <AuditActorPicker
      value={null}
      resetKey={0}
      onSelect={onSelect}
      onClear={onClear}
      {...props}
    />,
  );
  return { onSelect, onClear, ...view };
}

const input = () => screen.getByRole('combobox');

async function search(text) {
  fireEvent.change(input(), { target: { value: text } });
  await act(async () => { jest.advanceTimersByTime(300); });
}

describe('семантика combobox', () => {
  test('поле имеет подпись и роль combobox', () => {
    setup();
    expect(screen.getByLabelText('Участник')).toBe(input());
    expect(input()).toHaveAttribute('aria-autocomplete', 'list');
  });

  test('aria-expanded отражает состояние списка', async () => {
    setup();
    expect(input()).toHaveAttribute('aria-expanded', 'false');
    await search('Тест');
    await screen.findByRole('listbox');
    expect(input()).toHaveAttribute('aria-expanded', 'true');
  });

  test('список — listbox, элементы — option', async () => {
    setup();
    await search('Тест');
    const listbox = await screen.findByRole('listbox');
    expect(screen.getAllByRole('option')).toHaveLength(2);
    expect(input()).toHaveAttribute('aria-controls', listbox.id);
  });

  test('короткая строка список не открывает', async () => {
    setup();
    await search('Т');
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(getUsers).not.toHaveBeenCalled();
  });
});

describe('клавиатура', () => {
  test('ArrowDown отмечает активный вариант через aria-activedescendant', async () => {
    setup();
    await search('Тест');
    await screen.findByRole('listbox');
    expect(screen.getAllByRole('option')).toHaveLength(2);

    fireEvent.keyDown(input(), { key: 'ArrowDown' });
    const [first] = screen.getAllByRole('option');
    expect(first).toHaveAttribute('aria-selected', 'true');
    expect(input()).toHaveAttribute('aria-activedescendant', first.id);
  });

  test('ArrowDown/ArrowUp двигают выделение', async () => {
    setup();
    await search('Тест');
    await screen.findByRole('listbox');
    expect(screen.getAllByRole('option')).toHaveLength(2);

    fireEvent.keyDown(input(), { key: 'ArrowDown' });
    fireEvent.keyDown(input(), { key: 'ArrowDown' });
    expect(screen.getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(input(), { key: 'ArrowUp' });
    expect(screen.getAllByRole('option')[0]).toHaveAttribute('aria-selected', 'true');
  });

  test('Enter выбирает активный вариант', async () => {
    const { onSelect } = setup();
    await search('Тест');
    await screen.findByRole('listbox');
    expect(screen.getAllByRole('option')).toHaveLength(2);

    fireEvent.keyDown(input(), { key: 'ArrowDown' });
    fireEvent.keyDown(input(), { key: 'Enter' });

    expect(onSelect).toHaveBeenCalledWith(SELECTED);
  });

  test('Escape закрывает список, не выбирая', async () => {
    const { onSelect } = setup();
    await search('Тест');
    await screen.findByRole('listbox');

    fireEvent.keyDown(input(), { key: 'Escape' });
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(onSelect).not.toHaveBeenCalled();
  });
});

describe('выбор и безопасная проекция', () => {
  test('onSelect получает только uuid, ФИО, маскированный email и флаг удаления', async () => {
    const { onSelect } = setup();
    await search('Тест');
    await screen.findByRole('listbox');
    expect(screen.getAllByRole('option')).toHaveLength(2);

    fireEvent.mouseDown(screen.getAllByRole('option')[0]);

    const [actor] = onSelect.mock.calls[0];
    expect(Object.keys(actor).sort()).toEqual([
      'emailMasked', 'fullName', 'isDeleted', 'uuid',
    ]);
    expect(actor).not.toHaveProperty('id');
    expect(actor.emailMasked).toBe('t***@example.test');
  });

  test('полный email не отображается ни в одном варианте', async () => {
    setup();
    await search('Тест');
    await screen.findByRole('listbox');
    expect(screen.getAllByRole('option')).toHaveLength(2);

    expect(screen.getByRole('listbox').textContent).not.toContain('testovyy@');
    expect(screen.getByRole('listbox').textContent).toContain('t***@example.test');
  });

  test('удалённый аккаунт помечен в списке', async () => {
    setup();
    await search('Тест');
    await screen.findByRole('listbox');
    expect(screen.getAllByRole('option')).toHaveLength(2);
    expect(screen.getAllByRole('option')[1].textContent).toContain('Удалён');
  });

  test('после выбора список закрывается и строка поиска очищается', async () => {
    setup();
    await search('Тест');
    await screen.findByRole('listbox');
    expect(screen.getAllByRole('option')).toHaveLength(2);

    fireEvent.mouseDown(screen.getAllByRole('option')[0]);

    expect(screen.queryByRole('listbox')).toBeNull();
    expect(input()).toHaveValue('');
  });
});

describe('состояния поиска', () => {
  test('во время загрузки показан индикатор', async () => {
    getUsers.mockImplementationOnce(() => new Promise(() => {}));
    setup();
    await search('Тест');
    expect(screen.getByText('Поиск…')).toBeInTheDocument();
  });

  test('ошибка показывается в списке', async () => {
    getUsers.mockRejectedValueOnce(new Error('Сервис недоступен'));
    setup();
    await search('Тест');
    expect(await screen.findByText('Сервис недоступен')).toBeInTheDocument();
  });

  test('пустая выдача показывает сообщение', async () => {
    getUsers.mockResolvedValueOnce({ items: [], total: 0 });
    setup();
    await search('Тест');
    expect(await screen.findByText('Никого не найдено')).toBeInTheDocument();
  });
});

describe('controlled-состояние и сброс', () => {
  test('выбранный участник рисуется из value, а не из своего состояния', () => {
    setup({ value: SELECTED });
    expect(screen.getByText('Тестовый Пользователь')).toBeInTheDocument();
    expect(screen.getByText('t***@example.test')).toBeInTheDocument();
  });

  test('кнопка сброса вызывает onClear', () => {
    const { onClear } = setup({ value: SELECTED });
    fireEvent.click(screen.getByRole('button', { name: 'Сбросить пользователя' }));
    expect(onClear).toHaveBeenCalled();
  });

  test('value=null + новый resetKey убирают подпись, строку и выдачу', async () => {
    const { rerender } = setup({ value: SELECTED });
    await search('Тест');
    await screen.findByRole('listbox');

    rerender(
      <AuditActorPicker
        value={null}
        resetKey={1}
        onSelect={jest.fn()}
        onClear={jest.fn()}
      />,
    );

    expect(screen.queryByText('Тестовый Пользователь')).toBeNull();
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(input()).toHaveValue('');
  });

  test('после внешнего сброса фокус возвращается в поле', async () => {
    const { rerender } = setup({ value: SELECTED });

    rerender(
      <AuditActorPicker
        value={null}
        resetKey={7}
        onSelect={jest.fn()}
        onClear={jest.fn()}
      />,
    );

    await waitFor(() => expect(input()).toHaveFocus());
  });

  test('при неизменном value компонент не «запоминает» свой выбор', async () => {
    setup({ value: null });
    await search('Тест');
    await screen.findByRole('listbox');
    expect(screen.getAllByRole('option')).toHaveLength(2);

    fireEvent.mouseDown(screen.getAllByRole('option')[0]);

    // value осталось null — подписи выбранного участника быть не должно.
    expect(screen.queryByRole('button', { name: 'Сбросить пользователя' })).toBeNull();
  });
});
