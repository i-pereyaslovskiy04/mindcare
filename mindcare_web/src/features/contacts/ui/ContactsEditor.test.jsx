import fs from 'fs';
import path from 'path';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ContactsEditor from './ContactsEditor';
import useMyContacts from '../hooks/useMyContacts';
import { getMyContacts, saveMyContacts } from '../../../api/contacts.api';

jest.mock('../../../api/contacts.api');

const CATALOG = {
  types: [
    { code: 'phone', label: 'Телефон', service_kind: null },
    { code: 'email', label: 'Email', service_kind: null },
    { code: 'messenger', label: 'Мессенджер', service_kind: 'messenger' },
    { code: 'social', label: 'Социальная сеть', service_kind: 'social' },
    { code: 'website', label: 'Сайт', service_kind: null },
    { code: 'other', label: 'Другое', service_kind: null },
  ],
  services: {
    messenger: [
      { code: 'telegram', label: 'Telegram' },
      { code: 'whatsapp', label: 'WhatsApp' },
      { code: 'other', label: 'Другой мессенджер' },
    ],
    social: [
      { code: 'vk', label: 'VK' },
      { code: 'other', label: 'Другая соцсеть' },
    ],
  },
};
const LIMITS = { max_items: 2, label_max: 80, value_max: 500 };

function make(over = {}) {
  return {
    status: 'ready',
    loadError: '',
    retryLoad: jest.fn(),
    rows: [],
    limits: LIMITS,
    catalog: CATALOG,
    dirty: false,
    canAdd: true,
    fieldErrors: {},
    saveState: 'idle',
    saveMessage: '',
    conflict: null,
    focusTarget: null,
    addRow: jest.fn(),
    updateRow: jest.fn(),
    changeMethod: jest.fn(),
    clearLabel: jest.fn(),
    removeRow: jest.fn(),
    revert: jest.fn(),
    save: jest.fn(),
    overwrite: jest.fn(),
    loadSaved: jest.fn(),
    ...over,
  };
}

const row = (over = {}) => ({
  id: 'r1', type: 'phone', service: '', value: '+79001234567', label: '', ...over,
});

const renderEditor = (contacts) => render(
  <ContactsEditor contacts={contacts} audienceNote="Доступно психологу." idPrefix="t" />,
);

const methodControl = (group) => within(group).getByRole('button', { name: 'Способ связи' });

function chooseMethod(group, optionName) {
  fireEvent.click(methodControl(group));
  fireEvent.mouseDown(screen.getByRole('option', { name: optionName }));
}

describe('ContactsEditor', () => {
  it('показывает загрузку и ошибку загрузки с повтором', async () => {
    const { rerender } = renderEditor(make({ status: 'loading' }));
    expect(screen.getByRole('status')).toHaveTextContent('Загрузка контактов');
    const contacts = make({ status: 'loadError', loadError: 'нет сети' });
    rerender(<ContactsEditor contacts={contacts} audienceNote="x" />);
    expect(screen.getByRole('alert')).toHaveTextContent('нет сети');
    await userEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(contacts.retryLoad).toHaveBeenCalled();
  });

  it('показывает подпись аудитории и пустое состояние; общего абзаца про email нет', () => {
    renderEditor(make());
    expect(screen.getByText('Доступно психологу.')).toBeInTheDocument();
    expect(screen.getByText(/Дополнительных контактов пока нет/)).toBeInTheDocument();
    expect(screen.queryByText(/не меняет адрес аккаунта/)).toBeNull();
  });

  it.each([
    [0, false],
    [7, false],
    [8, true],
    [10, true],
  ])('счётчик при %i из 10: видим — %s; live-сообщение есть всегда', (count, visible) => {
    const rows = Array.from({ length: count }, (_, i) => row({ id: `r${i}` }));
    renderEditor(make({ rows, limits: { ...LIMITS, max_items: 10 }, canAdd: count < 10 }));
    const counter = screen.getByText(`Добавлено ${count} из 10`);
    expect(counter).toHaveAttribute('aria-live', 'polite');
    expect(counter.classList.contains('visually-hidden')).toBe(!visible);
  });

  it('пояснение про дополнительный email — только у строки с Email', () => {
    renderEditor(make({
      rows: [row({ id: 'a' }), row({ id: 'b', type: 'email', value: 'me@example.org' })],
    }));
    const [phone, email] = screen.getAllByRole('group');
    expect(within(email).getByLabelText('Email'))
      .toHaveAccessibleDescription('Только для связи, не используется для входа');
    expect(within(phone).getByLabelText('Номер телефона'))
      .not.toHaveAccessibleDescription(/для входа/);
    expect(screen.getAllByText('Только для связи, не используется для входа')).toHaveLength(1);
    // Длинного пояснения про адрес аккаунта и восстановление пароля в строке нет.
    expect(screen.queryByText(/адрес аккаунта|восстановления пароля/)).toBeNull();
  });

  it('обычный контакт — два поля: «Способ связи» и значение; «Подписи» нет', () => {
    renderEditor(make({ rows: [row()] }));
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    expect(methodControl(group)).toHaveTextContent('Телефон');
    expect(within(group).getByLabelText('Номер телефона')).toHaveValue('+79001234567');
    expect(within(group).queryByLabelText(/Подпись/)).toBeNull();
    expect(within(group).queryByLabelText('Название')).toBeNull();
    expect(screen.queryByText(/Подпись \(необязательно\)/)).toBeNull();
    expect(screen.queryByText(/рабочий, для срочных вопросов/)).toBeNull();
    // Пара «тип + сервис» заменена единым селектором.
    expect(within(group).queryByText('Сервис')).toBeNull();
    expect(within(group).queryByRole('button', { name: /^Тип$/ })).toBeNull();
  });

  it.each([
    [{ type: 'phone', service: '' }, 'Телефон'],
    [{ type: 'email', service: '' }, 'Email'],
    [{ type: 'messenger', service: 'telegram' }, 'Telegram'],
    [{ type: 'messenger', service: 'other' }, 'Другой мессенджер'],
    [{ type: 'social', service: 'vk' }, 'VK'],
    [{ type: 'social', service: 'other' }, 'Другая соцсеть'],
    [{ type: 'website', service: '' }, 'Сайт'],
    [{ type: 'other', service: '' }, 'Другое'],
  ])('сохранённый %j отображается вариантом «%s»', (pair, label) => {
    renderEditor(make({ rows: [row(pair)] }));
    expect(methodControl(screen.getByRole('group', { name: 'Контакт 1' }))).toHaveTextContent(label);
  });

  it('новому контакту предлагается короткий список (только из каталога)', () => {
    renderEditor(make({ rows: [row()] }));
    fireEvent.click(methodControl(screen.getByRole('group', { name: 'Контакт 1' })));
    // MAX в тестовом каталоге нет — вариант не выдумывается.
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Телефон', 'Telegram', 'VK', 'Email', 'WhatsApp', 'Другое',
    ]);
  });

  it.each([
    [{ type: 'website', service: '' }, 'Сайт'],
    [{ type: 'social', service: 'other', label: 'Сеть' }, 'Другая соцсеть'],
    [{ type: 'messenger', service: 'other', label: 'Сервис' }, 'Другой мессенджер'],
  ])('скрытый сохранённый способ %j отображается и остаётся выбираемым в своей строке', (pair, label) => {
    renderEditor(make({ rows: [row({ id: 'a' }), row({ id: 'b', ...pair, value: 'x' })] }));
    const [plain, legacy] = screen.getAllByRole('group');
    expect(methodControl(legacy)).toHaveTextContent(label);

    fireEvent.click(methodControl(legacy));
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Телефон', 'Telegram', 'VK', 'Email', 'WhatsApp', 'Другое', label,
    ]);
    fireEvent.click(methodControl(legacy));

    // В соседней строке скрытого способа нет.
    fireEvent.click(methodControl(plain));
    expect(screen.queryByRole('option', { name: label })).toBeNull();
  });

  it('сохранённый скрытый способ остаётся в списке строки и после смены способа', () => {
    renderEditor(make({
      rows: [row({ id: 'a', type: 'messenger', service: 'telegram', value: '@me' })],
      savedItems: [{ id: 'a', type: 'website', service: null, value: 'example.org', label: null }],
    }));
    fireEvent.click(methodControl(screen.getByRole('group', { name: 'Контакт 1' })));
    expect(screen.getByRole('option', { name: 'Сайт' })).toBeInTheDocument();
  });

  it('подпись, placeholder и режим ввода значения соответствуют способу связи', () => {
    renderEditor(make({
      rows: [
        row({ id: 'a', type: 'phone', value: '' }),
        row({ id: 'b', type: 'email', value: '' }),
        row({ id: 'c', type: 'website', value: '' }),
        row({ id: 'd', type: 'messenger', service: 'telegram', value: '' }),
      ],
    }));
    const [phone, email, site, messenger] = screen.getAllByRole('group');
    const phoneInput = within(phone).getByLabelText('Номер телефона');
    expect(phoneInput).toHaveAttribute('type', 'tel');
    expect(phoneInput).toHaveAttribute('inputmode', 'tel');
    expect(phoneInput).toHaveAttribute('placeholder');
    expect(within(email).getByLabelText('Email')).toHaveAttribute('inputmode', 'email');
    expect(within(site).getByLabelText('Адрес сайта')).toHaveAttribute('inputmode', 'url');
    expect(within(messenger).getByLabelText('Имя пользователя, номер или ссылка')).toHaveAttribute('placeholder', '@username');
  });

  it('«Название» показывается только у вариантов «Другой …» и ограничено label_max', () => {
    renderEditor(make({
      rows: [
        row({ id: 'a', type: 'messenger', service: 'telegram', value: '@a', label: 'рабочий' }),
        row({ id: 'b', type: 'messenger', service: 'other', value: 'x', label: 'Мой сервис' }),
        row({ id: 'c', type: 'social', service: 'other', value: 'y', label: 'Сеть' }),
        row({ id: 'd', type: 'other', value: 'z', label: 'Особый' }),
      ],
    }));
    const [telegram, otherMessenger, otherSocial, other] = screen.getAllByRole('group');
    expect(within(telegram).queryByLabelText('Название')).toBeNull();
    // Скрытая прежняя подпись обычного контакта на экране не показывается.
    expect(within(telegram).queryByDisplayValue('рабочий')).toBeNull();
    [otherMessenger, otherSocial, other].forEach((group) => {
      const name = within(group).getByLabelText('Название');
      expect(name).toHaveAttribute('maxlength', '80');
    });
    expect(within(otherMessenger).getByLabelText('Название')).toHaveValue('Мой сервис');
  });

  it('ввод, смена способа и удаление вызывают действия хука', async () => {
    const contacts = make({ rows: [row({ value: '' })] });
    renderEditor(contacts);
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    await userEvent.type(within(group).getByLabelText('Номер телефона'), '7');
    // Способ «Телефон» — маска основного телефона.
    expect(contacts.updateRow).toHaveBeenCalledWith('r1', { value: '+7' });
    chooseMethod(group, 'Telegram');
    expect(contacts.changeMethod).toHaveBeenCalledWith('r1', 'messenger:telegram');
    await userEvent.click(screen.getByRole('button', { name: 'Удалить контакт 1' }));
    expect(contacts.removeRow).toHaveBeenCalledWith('r1');
  });

  it('на лимите «Добавить» заблокирована с пояснением', () => {
    renderEditor(make({ rows: [row(), row({ id: 'r2' })], canAdd: false }));
    expect(screen.getByRole('button', { name: /Добавить контакт/ })).toBeDisabled();
    expect(screen.getByText(/не более 2/)).toBeInTheDocument();
  });

  it('кнопки удаления имеют доступные имена; видимого «Контакт N» нет, имя группы осталось', () => {
    renderEditor(make({ rows: [row(), row({ id: 'r2' })] }));
    const [first, second] = screen.getAllByRole('group');
    expect(first).toHaveAccessibleName('Контакт 1');
    expect(second).toHaveAccessibleName('Контакт 2');
    const remove = within(first).getByRole('button', { name: 'Удалить контакт 1' });
    expect(remove).toHaveAttribute('title', 'Удалить контакт');
    expect(remove).toHaveClass('deleteButton');
    expect(within(second).getByRole('button', { name: 'Удалить контакт 2' })).toBeInTheDocument();
    expect(screen.queryByText(/^Контакт \d$/)).toBeNull();
  });

  it('ошибка значения привязана к полю', () => {
    renderEditor(make({
      rows: [row()],
      fieldErrors: { r1: { value: 'Введите корректный номер' } },
    }));
    const input = screen.getByLabelText('Номер телефона');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription(/Введите корректный номер/);
  });

  it('ошибка способа связи привязана к селектору', () => {
    renderEditor(make({
      rows: [row({ type: 'messenger', service: '' })],
      fieldErrors: { r1: { service: 'Выберите способ связи' } },
    }));
    const control = methodControl(screen.getByRole('group', { name: 'Контакт 1' }));
    expect(control).toHaveAttribute('aria-invalid', 'true');
    expect(control).toHaveAccessibleDescription('Выберите способ связи');
  });

  it.each([
    [{ field: 'service' }, { type: 'messenger', service: 'other', label: '' }, 'Способ связи'],
    [{ field: 'type' }, { type: 'phone' }, 'Способ связи'],
    [{ field: 'value' }, { type: 'phone' }, 'Номер телефона'],
    [{ field: 'label' }, { type: 'messenger', service: 'other', label: '' }, 'Название'],
  ])('фокус по ошибке %j переходит на видимый контрол', (target, rowOver, name) => {
    renderEditor(make({
      rows: [row(rowOver)],
      focusTarget: { id: 'r1', n: 1, ...target },
    }));
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    const el = name === 'Способ связи'
      ? methodControl(group)
      : within(group).getByLabelText(name);
    expect(el).toHaveFocus();
  });

  it('ошибка скрытой подписи: сообщение и действие «Удалить прежнюю подпись»', () => {
    const contacts = make({
      rows: [row({ label: 'старая подпись' })],
      fieldErrors: { r1: { hiddenLabel: 'Слишком длинное значение' } },
      focusTarget: { id: 'r1', field: 'label', n: 1 },
    });
    renderEditor(contacts);
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    expect(within(group).getByRole('alert')).toHaveTextContent('старая подпись');
    const action = within(group).getByRole('button', { name: 'Удалить прежнюю подпись' });
    expect(action).toHaveFocus();
    fireEvent.click(action);
    expect(contacts.clearLabel).toHaveBeenCalledWith('r1');
  });

  it('сохранение — по кнопке; кнопки зависят от dirty', async () => {
    const contacts = make({ rows: [row()], dirty: true });
    renderEditor(contacts);
    expect(screen.getByText('Есть несохранённые изменения')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    expect(contacts.save).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button', { name: 'Отменить изменения' }));
    expect(contacts.revert).toHaveBeenCalled();
  });

  it('без изменений кнопки сохранения и отмены отключены', () => {
    renderEditor(make({ rows: [row()] }));
    expect(screen.getByRole('button', { name: 'Сохранить' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Отменить изменения' })).toBeDisabled();
  });

  it('успех объявляется role=status, ошибка — role=alert', () => {
    const { rerender } = renderEditor(make({ saveState: 'saved' }));
    expect(screen.getByRole('status')).toHaveTextContent('Контакты сохранены');
    rerender(
      <ContactsEditor contacts={make({ saveState: 'error', saveMessage: 'Не удалось' })} audienceNote="x" />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Не удалось');
  });

  it('конфликт: два действия и сводка сохранённого с подписью способа связи', async () => {
    const contacts = make({
      rows: [row()],
      dirty: true,
      saveState: 'conflict',
      conflict: {
        currentVersion: 4,
        saved: {
          version: 4,
          items: [{ id: 'z', type: 'messenger', service: 'telegram', value: '@z', label: null }],
        },
      },
    });
    renderEditor(contacts);
    expect(screen.getByRole('alert')).toHaveTextContent('изменены в другом окне');
    fireEvent.click(screen.getByText(/Что сейчас сохранено \(1\)/));
    expect(screen.getByText('Telegram · @z')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Сохранить' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Перезаписать моими правками' }));
    expect(contacts.overwrite).toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Загрузить сохранённые' }));
    expect(contacts.loadSaved).toHaveBeenCalled();
  });

  it('во время сохранения поля отключены', () => {
    renderEditor(make({ rows: [row()], dirty: true, saveState: 'saving' }));
    expect(screen.getByLabelText('Номер телефона')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Удалить контакт 1' })).toBeDisabled();
    expect(methodControl(screen.getByRole('group', { name: 'Контакт 1' }))).toBeDisabled();
  });

  it('контакт с типом/сервисом вне каталога не ломает форму', () => {
    renderEditor(make({ rows: [row({ type: 'messenger', service: 'icq' })] }));
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    expect(methodControl(group)).toHaveTextContent('messenger / icq');
  });
});

// ── Реальный хук: сквозные сценарии ──────────────────────────────────────────

function Connected() {
  const contacts = useMyContacts({ enabled: true });
  return <ContactsEditor contacts={contacts} audienceNote="Доступно психологу." idPrefix="t" />;
}

const snapshot = (items = [], version = 0) => ({
  version, updated_at: null, items, limits: { max_items: 10, label_max: 80, value_max: 500 }, catalog: CATALOG,
});

async function openConnected(items = [], version = 0) {
  getMyContacts.mockResolvedValue(snapshot(items, version));
  render(<Connected />);
  await screen.findByRole('button', { name: /Добавить контакт/ });
}

function addContact() {
  fireEvent.click(screen.getByRole('button', { name: /Добавить контакт/ }));
  const groups = screen.getAllByRole('group');
  return groups[groups.length - 1];
}

const saveButton = () => screen.getByRole('button', { name: 'Сохранить' });
const lastPayload = () => saveMyContacts.mock.calls[saveMyContacts.mock.calls.length - 1][0];

describe('ContactsEditor с реальным хуком', () => {
  beforeEach(() => {
    saveMyContacts.mockImplementation(async ({ version, items }) => ({
      ...snapshot(items, version + 1), changed: true,
    }));
  });

  it.each([
    ['Телефон', 'Номер телефона', '+7 (900) 123-45-67', { type: 'phone', service: null }],
    ['Email', 'Email', 'me@example.org', { type: 'email', service: null }],
    ['Telegram', 'Имя пользователя, номер или ссылка', '@my_name', { type: 'messenger', service: 'telegram' }],
    ['WhatsApp', 'Номер телефона или ссылка', '+79001234567', { type: 'messenger', service: 'whatsapp' }],
    ['VK', 'Имя пользователя или ссылка', 'https://vk.com/id1', { type: 'social', service: 'vk' }],
  ])('способ «%s» отправляет type/service и label:null', async (option, valueLabel, value, expected) => {
    await openConnected();
    const group = addContact();
    chooseMethod(group, option);
    fireEvent.change(within(group).getByLabelText(valueLabel), { target: { value } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(saveMyContacts).toHaveBeenCalledTimes(1));
    expect(lastPayload()).toEqual({
      version: 0,
      items: [{ id: expect.stringMatching(/^[0-9a-f-]{36}$/), value, label: null, ...expected }],
    });
    expect(await screen.findByText('Контакты сохранены.')).toBeInTheDocument();
  });

  it('новый обычный контакт без выбора способа — телефон, label:null', async () => {
    await openConnected();
    const group = addContact();
    expect(methodControl(group)).toHaveTextContent('Телефон');
    fireEvent.change(within(group).getByLabelText('Номер телефона'), { target: { value: '+79001234567' } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(saveMyContacts).toHaveBeenCalled());
    expect(lastPayload().items[0]).toMatchObject({
      type: 'phone', service: null, label: null, value: '+7 (900) 123-45-67',
    });
  });

  it('«Другое» без названия: ошибка у «Название», фокус на нём; с названием — сохраняется', async () => {
    await openConnected();
    const group = addContact();
    chooseMethod(group, 'Другое');
    fireEvent.change(within(group).getByLabelText('Контакт'), { target: { value: 'в кабинете 5' } });
    fireEvent.click(saveButton());

    const name = await within(group).findByLabelText('Название');
    expect(name).toHaveFocus();
    expect(name).toHaveAttribute('aria-invalid', 'true');
    expect(saveMyContacts).not.toHaveBeenCalled();

    fireEvent.change(name, { target: { value: 'Кабинет' } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(saveMyContacts).toHaveBeenCalledTimes(1));
    expect(lastPayload().items[0]).toMatchObject({
      type: 'other', service: null, value: 'в кабинете 5', label: 'Кабинет',
    });
  });

  it('сохранённая «Другая соцсеть» требует «Название» и сохраняется без потери данных', async () => {
    const id = '22222222-2222-4222-8222-222222222222';
    await openConnected([{ id, type: 'social', service: 'other', value: 'my-id', label: 'Сеть' }], 2);
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    expect(methodControl(group)).toHaveTextContent('Другая соцсеть');
    const name = within(group).getByLabelText('Название');
    expect(name).toHaveValue('Сеть');

    fireEvent.change(name, { target: { value: '' } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(name).toHaveAttribute('aria-invalid', 'true'));
    expect(saveMyContacts).not.toHaveBeenCalled();

    fireEvent.change(name, { target: { value: 'Моя сеть' } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(saveMyContacts).toHaveBeenCalledTimes(1));
    expect(lastPayload()).toEqual({
      version: 2,
      items: [{ id, type: 'social', service: 'other', value: 'my-id', label: 'Моя сеть' }],
    });
  });

  it('сохранённый сайт: редактируется и сохраняется своим типом; к нему можно вернуться после смены', async () => {
    const id = '33333333-3333-4333-8333-333333333333';
    await openConnected([{ id, type: 'website', service: null, value: 'example.org', label: null }], 5);
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    expect(methodControl(group)).toHaveTextContent('Сайт');

    chooseMethod(group, 'Telegram');
    expect(methodControl(group)).toHaveTextContent('Telegram');
    chooseMethod(group, 'Сайт');
    expect(methodControl(group)).toHaveTextContent('Сайт');

    fireEvent.change(within(group).getByLabelText('Адрес сайта'), { target: { value: 'https://example.org/me' } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(saveMyContacts).toHaveBeenCalledTimes(1));
    expect(lastPayload()).toEqual({
      version: 5,
      items: [{ id, type: 'website', service: null, value: 'https://example.org/me', label: null }],
    });
  });

  it('прежняя подпись обычного контакта сохраняется при редактировании и сохранении', async () => {
    await openConnected([
      { id: '11111111-1111-4111-8111-111111111111', type: 'phone', service: null, value: '+79001234567', label: 'рабочий' },
    ], 3);
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    expect(within(group).queryByDisplayValue('рабочий')).toBeNull();
    fireEvent.change(within(group).getByLabelText('Номер телефона'), { target: { value: '+79001112233' } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(saveMyContacts).toHaveBeenCalledTimes(1));
    expect(lastPayload()).toEqual({
      version: 3,
      items: [{
        id: '11111111-1111-4111-8111-111111111111',
        type: 'phone', service: null, value: '+7 (900) 111-22-33', label: 'рабочий',
      }],
    });
  });

  it('смена способа убирает прежний сервис: Telegram → Email → payload без service', async () => {
    await openConnected([
      { id: '11111111-1111-4111-8111-111111111111', type: 'messenger', service: 'telegram', value: '@name', label: null },
    ], 1);
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    expect(methodControl(group)).toHaveTextContent('Telegram');
    chooseMethod(group, 'Email');
    fireEvent.change(within(group).getByLabelText('Email'), { target: { value: 'me@example.org' } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(saveMyContacts).toHaveBeenCalledTimes(1));
    expect(lastPayload().items[0]).toMatchObject({ type: 'email', service: null, value: 'me@example.org' });
  });

  it('ошибка сервера по способу связи: фокус на селекторе, ошибка связана с контролом', async () => {
    await openConnected();
    const group = addContact();
    fireEvent.change(within(group).getByLabelText('Номер телефона'), { target: { value: '+79001234567' } });
    saveMyContacts.mockRejectedValueOnce(Object.assign(new Error('x'), {
      status: 422, body: { errors: [{ index: 0, field: 'service', code: 'invalid_service' }] },
    }));
    fireEvent.click(saveButton());
    const control = methodControl(group);
    await waitFor(() => expect(control).toHaveFocus());
    expect(control).toHaveAttribute('aria-invalid', 'true');
    expect(control).toHaveAccessibleDescription('Выберите способ связи');
  });

  it('ошибка сервера по скрытой подписи → «Удалить прежнюю подпись» → успешный повтор', async () => {
    const id = '11111111-1111-4111-8111-111111111111';
    await openConnected([{ id, type: 'phone', service: null, value: '+79001234567', label: 'старая подпись' }], 2);
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    fireEvent.change(within(group).getByLabelText('Номер телефона'), { target: { value: '+79001112233' } });
    saveMyContacts.mockRejectedValueOnce(Object.assign(new Error('x'), {
      status: 422, body: { errors: [{ index: 0, field: 'label', code: 'too_long' }] },
    }));
    fireEvent.click(saveButton());

    const action = await within(group).findByRole('button', { name: 'Удалить прежнюю подпись' });
    await waitFor(() => expect(action).toHaveFocus());
    expect(within(group).getByRole('alert')).toHaveTextContent('старая подпись');
    // Автоматически данные не стираются: подпись всё ещё в черновике.
    expect(saveMyContacts).toHaveBeenCalledTimes(1);
    expect(lastPayload().items[0].label).toBe('старая подпись');

    fireEvent.click(action);
    expect(within(group).queryByRole('button', { name: 'Удалить прежнюю подпись' })).toBeNull();
    fireEvent.click(saveButton());
    await waitFor(() => expect(saveMyContacts).toHaveBeenCalledTimes(2));
    expect(lastPayload()).toEqual({
      version: 2,
      items: [{ id, type: 'phone', service: null, value: '+7 (900) 111-22-33', label: null }],
    });
    expect(await screen.findByText('Контакты сохранены.')).toBeInTheDocument();
  });

  it('сохранение → повторная загрузка → конфликт версий и загрузка сохранённых', async () => {
    const id = '11111111-1111-4111-8111-111111111111';
    await openConnected([{ id, type: 'phone', service: null, value: '+79001234567', label: null }], 1);
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    fireEvent.change(within(group).getByLabelText('Номер телефона'), { target: { value: '+79001112233' } });
    saveMyContacts.mockRejectedValueOnce(Object.assign(new Error('конфликт'), {
      status: 409, code: 'contacts_version_conflict', body: { current_version: 4 },
    }));
    getMyContacts.mockResolvedValueOnce(snapshot([
      { id, type: 'messenger', service: 'telegram', value: '@remote', label: null },
    ], 4));
    fireEvent.click(saveButton());

    expect(await screen.findByText(/изменены в другом окне/)).toBeInTheDocument();
    // Черновик пользователя на месте.
    expect(within(group).getByLabelText('Номер телефона')).toHaveValue('+7 (900) 111-22-33');
    fireEvent.click(await screen.findByText(/Что сейчас сохранено \(1\)/));
    expect(screen.getByText('Telegram · @remote')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Загрузить сохранённые' }));
    const reloaded = await screen.findByRole('group', { name: 'Контакт 1' });
    expect(methodControl(reloaded)).toHaveTextContent('Telegram');
    expect(within(reloaded).getByLabelText('Имя пользователя, номер или ссылка')).toHaveValue('@remote');
  });

  it('конфликт: «Перезаписать моими правками» отправляет актуальную версию', async () => {
    const id = '11111111-1111-4111-8111-111111111111';
    await openConnected([{ id, type: 'phone', service: null, value: '+79001234567', label: null }], 1);
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    fireEvent.change(within(group).getByLabelText('Номер телефона'), { target: { value: '+79001112233' } });
    saveMyContacts.mockRejectedValueOnce(Object.assign(new Error('конфликт'), {
      status: 409, code: 'contacts_version_conflict', body: { current_version: 4 },
    }));
    getMyContacts.mockResolvedValueOnce(snapshot([
      { id, type: 'phone', service: null, value: '+79995556677', label: null },
    ], 4));
    fireEvent.click(saveButton());
    await screen.findByText(/изменены в другом окне/);
    await screen.findByText(/Что сейчас сохранено/);

    fireEvent.click(screen.getByRole('button', { name: 'Перезаписать моими правками' }));
    await waitFor(() => expect(saveMyContacts).toHaveBeenCalledTimes(2));
    expect(lastPayload().version).toBe(4);
    expect(lastPayload().items[0].value).toBe('+7 (900) 111-22-33');
  });
});

// Ширины jsdom не моделирует — проверяем сами правила раскладки (визуально —
// ручной smoke).
describe('ContactsEditor.module.css: компактная строка', () => {
  const css = fs.readFileSync(path.join(__dirname, 'ContactsEditor.module.css'), 'utf8');
  const rule = (selector, source = css) => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const match = new RegExp(`(^|\\n)\\s*${escaped}\\s*\\{([^}]*)\\}`).exec(source);
    return match ? match[2] : '';
  };
  const mediaBlock = (query) => {
    const start = css.indexOf(`@media ${query} {`);
    expect(start).toBeGreaterThanOrEqual(0);
    const next = css.indexOf('@media', start + 1);
    return css.slice(start, next === -1 ? undefined : next);
  };

  it('desktop: одна строка «способ | значение | удалить», без карточки вокруг', () => {
    expect(rule('.row')).toMatch(/grid-template-columns:\s*minmax\(180px, 220px\) minmax\(0, 1fr\) 40px/);
    // «Удалить» — той же высоты, что поле, без лишнего разрыва.
    expect(rule('.deleteCell .deleteButton')).toMatch(/width:\s*40px;[^}]*height:\s*40px/);
    expect(rule('.row')).not.toMatch(/background/);
    expect(rule('.row')).not.toMatch(/border:/);
    expect(rule('.item + .item')).toMatch(/border-top:\s*1px solid var\(--nav-border\)/);
    expect(rule('.deleteCell')).toMatch(/grid-column:\s*3/);
    expect(css).not.toMatch(/rowHead|rowTitle/);
  });

  it('<=560px: поля друг под другом, «Удалить» справа в верхней строке', () => {
    const block = mediaBlock('(max-width: 560px)');
    expect(rule('.row', block)).toMatch(/grid-template-columns:\s*minmax\(0, 1fr\) auto/);
    expect(block).toMatch(/\.deleteCell\s*\{[^}]*grid-column:\s*2;[^}]*grid-row:\s*1/);
    expect(block).toMatch(/\.valueField,\s*\.nameField\s*\{[^}]*grid-column:\s*1 \/ -1/);
  });

  it('сенсорный ввод: «Удалить» не меньше 44×44', () => {
    const block = mediaBlock('(hover: none)');
    expect(block).toMatch(/\.deleteButton\s*\{[^}]*width:\s*44px;[^}]*height:\s*44px/);
    expect(block).toMatch(/grid-template-columns:\s*minmax\(180px, 220px\) minmax\(0, 1fr\) 44px/);
  });

  it('зона сохранения отделена тонкой линией и отступом, без фона', () => {
    expect(rule('.saveZone')).toMatch(/border-top:\s*1px solid var\(--nav-border\)/);
    expect(rule('.saveZone')).toMatch(/padding-top:/);
    expect(rule('.saveZone')).not.toMatch(/background/);
    expect(rule('.dirty')).toMatch(/color:\s*var\(--on-surface-variant\)/);
    expect(rule('.actions')).toMatch(/flex-wrap:\s*wrap/);
  });
});

// ── Поле значения по способу связи ──────────────────────────────────────────

describe('ContactsEditor: поле значения по способу связи', () => {
  beforeEach(() => {
    saveMyContacts.mockImplementation(async ({ version, items }) => ({
      ...snapshot(items, version + 1), changed: true,
    }));
  });

  const valueInput = (group, label) => within(group).getByLabelText(label);

  it('«Телефон»: маска основного телефона, десятки цифр не вводятся', async () => {
    await openConnected();
    const group = addContact();
    const input = valueInput(group, 'Номер телефона');
    expect(input).toHaveAttribute('type', 'tel');
    expect(input).toHaveAttribute('placeholder', '+7 (949) 000-00-00');

    fireEvent.change(input, { target: { value: '89001234567' } });
    expect(input).toHaveValue('+7 (900) 123-45-67');

    fireEvent.change(input, { target: { value: '8445454545454121218448544812345678' } });
    expect(input).toHaveValue('+7 (445) 454-54-54');
    expect(input.value.replace(/\D/g, '')).toHaveLength(11);
  });

  it('недописанный номер не проходит проверку', async () => {
    await openConnected();
    const group = addContact();
    fireEvent.change(valueInput(group, 'Номер телефона'), { target: { value: '900123' } });
    expect(valueInput(group, 'Номер телефона')).toHaveValue('+7 (900) 123');
    fireEvent.click(saveButton());
    await waitFor(() => {
      expect(valueInput(group, 'Номер телефона')).toHaveAttribute('aria-invalid', 'true');
    });
    expect(saveMyContacts).not.toHaveBeenCalled();
  });

  it('сохранённый номер другой страны не переписывается в +7 и не принимает буквы', async () => {
    const id = '44444444-4444-4444-8444-444444444444';
    await openConnected([{ id, type: 'phone', service: null, value: '+380711234567', label: null }], 1);
    const input = valueInput(screen.getByRole('group', { name: 'Контакт 1' }), 'Номер телефона');
    fireEvent.change(input, { target: { value: '+3807112345678' } });
    expect(input).toHaveValue('+3807112345678');
    fireEvent.change(input, { target: { value: '+3807112345678abc' } });
    expect(input).toHaveValue('+3807112345678');
    fireEvent.change(input, { target: { value: '+38071123456789999999' } });
    expect(input).toHaveValue('+380711234567899');
  });

  it('вставка «+7 (234) 234-2выа34234234234234»: без букв и не длиннее маски', async () => {
    await openConnected();
    const group = addContact();
    const input = valueInput(group, 'Номер телефона');
    fireEvent.change(input, { target: { value: '+7 (234) 234-2выа34234234234234' } });
    expect(input).toHaveValue('+7 (234) 234-23-42');
    expect(input.value).not.toMatch(/\p{L}/u);
    expect(input.value.length).toBeLessThanOrEqual('+7 (949) 000-00-00'.length);
  });

  it('буквы в пустое телефонное поле не вводятся', async () => {
    await openConnected();
    const group = addContact();
    const input = valueInput(group, 'Номер телефона');
    fireEvent.change(input, { target: { value: 'abc' } });
    expect(input).toHaveValue('');
    fireEvent.change(input, { target: { value: 'тест' } });
    expect(input).toHaveValue('');
  });

  it.each([
    ['Email', 'Email'],
    ['Telegram', 'Имя пользователя, номер или ссылка'],
    ['VK', 'Имя пользователя или ссылка'],
    ['Другое', 'Контакт'],
    ['WhatsApp', 'Номер телефона или ссылка'],
  ])('«%s»: без телефонной маски — значение как введено', async (option, label) => {
    await openConnected();
    const group = addContact();
    chooseMethod(group, option);
    const input = valueInput(group, label);
    fireEvent.change(input, { target: { value: '89001234567' } });
    expect(input).toHaveValue('89001234567');
    expect(input).not.toHaveAttribute('type', 'tel');
  });

  it('Email: type=email, placeholder name@example.ru; строка цифр не проходит проверку', async () => {
    await openConnected();
    const group = addContact();
    chooseMethod(group, 'Email');
    const input = valueInput(group, 'Email');
    expect(input).toHaveAttribute('type', 'email');
    expect(input).toHaveAttribute('inputmode', 'email');
    expect(input).toHaveAttribute('placeholder', 'name@example.ru');

    fireEvent.change(input, { target: { value: '84454545454541212184485448' } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(input).toHaveAttribute('aria-invalid', 'true'));
    expect(input).toHaveAccessibleDescription(/Введите корректный email/);
    expect(saveMyContacts).not.toHaveBeenCalled();
  });

  it('WhatsApp: номер телефона без маски (контракт допускает и ссылку) — сохраняется как введён', async () => {
    await openConnected();
    const group = addContact();
    chooseMethod(group, 'WhatsApp');
    const input = valueInput(group, 'Номер телефона или ссылка');
    expect(input).toHaveAttribute('placeholder', '+7 (949) 000-00-00');
    fireEvent.change(input, { target: { value: 'https://wa.me/79001234567' } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(saveMyContacts).toHaveBeenCalledTimes(1));
    expect(lastPayload().items[0]).toMatchObject({
      type: 'messenger', service: 'whatsapp', value: 'https://wa.me/79001234567',
    });
  });

  it('смена способа очищает значение и ошибки, применяет подпись и проверку нового', async () => {
    await openConnected();
    const group = addContact();
    fireEvent.change(valueInput(group, 'Номер телефона'), { target: { value: '900123' } });
    fireEvent.click(saveButton());
    await waitFor(() => {
      expect(valueInput(group, 'Номер телефона')).toHaveAttribute('aria-invalid', 'true');
    });

    // Телефон → Telegram: номер очищен, ошибка снята, подпись и placeholder новые.
    chooseMethod(group, 'Telegram');
    const tg = valueInput(group, 'Имя пользователя, номер или ссылка');
    expect(tg).toHaveValue('');
    expect(tg).not.toHaveAttribute('aria-invalid');
    expect(tg).toHaveAttribute('placeholder', '@username');
    expect(within(group).queryByRole('alert')).toBeNull();

    // Telegram → Email: @username очищается.
    fireEvent.change(tg, { target: { value: '@ivan' } });
    chooseMethod(group, 'Email');
    const email = valueInput(group, 'Email');
    expect(email).toHaveValue('');
    expect(email).toHaveAttribute('type', 'email');

    // Проверка — по новому способу.
    fireEvent.change(email, { target: { value: '@ivan' } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(email).toHaveAttribute('aria-invalid', 'true'));
    expect(email).toHaveAccessibleDescription(/Введите корректный email/);
    expect(saveMyContacts).not.toHaveBeenCalled();
  });

  it('выбор уже выбранного способа и rerender значение не очищают', async () => {
    await openConnected();
    const group = addContact();
    fireEvent.change(valueInput(group, 'Номер телефона'), { target: { value: '9001234567' } });
    chooseMethod(group, 'Телефон');
    expect(valueInput(group, 'Номер телефона')).toHaveValue('+7 (900) 123-45-67');
    // Любое другое действие формы (rerender) значение не трогает.
    addContact();
    expect(valueInput(group, 'Номер телефона')).toHaveValue('+7 (900) 123-45-67');
  });

  it('загрузка сохранённого контакта не очищает значение', async () => {
    const id = '55555555-5555-4555-8555-555555555555';
    await openConnected([{ id, type: 'messenger', service: 'telegram', value: '@saved', label: null }], 3);
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    expect(valueInput(group, 'Имя пользователя, номер или ссылка')).toHaveValue('@saved');
    expect(saveButton()).toBeDisabled();
  });

  it('«Отменить изменения» возвращает значение, очищенное сменой способа', async () => {
    const id = '66666666-6666-4666-8666-666666666666';
    await openConnected([{ id, type: 'phone', service: null, value: '+79001234567', label: null }], 1);
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    chooseMethod(group, 'Telegram');
    expect(valueInput(group, 'Имя пользователя, номер или ссылка')).toHaveValue('');
    fireEvent.click(screen.getByRole('button', { name: 'Отменить изменения' }));
    const restored = screen.getByRole('group', { name: 'Контакт 1' });
    expect(methodControl(restored)).toHaveTextContent('Телефон');
    expect(valueInput(restored, 'Номер телефона')).toHaveValue('+79001234567');
  });

  it('у поля значения есть предел длины из limits', async () => {
    await openConnected();
    const group = addContact();
    chooseMethod(group, 'Другое');
    expect(valueInput(group, 'Контакт')).toHaveAttribute('maxlength', '500');
  });
});
