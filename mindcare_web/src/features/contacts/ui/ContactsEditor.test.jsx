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

  it('показывает подпись аудитории, счётчик и пустое состояние', () => {
    renderEditor(make());
    expect(screen.getByText('Доступно психологу.')).toBeInTheDocument();
    expect(screen.getByText(/Добавлено 0 из 2/)).toBeInTheDocument();
    expect(screen.getByText(/Дополнительных контактов пока нет/)).toBeInTheDocument();
    expect(screen.getByText(/не меняет адрес аккаунта/)).toBeInTheDocument();
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

  it('варианты строятся из каталога: ни одного лишнего и в порядке каталога', () => {
    renderEditor(make({ rows: [row()] }));
    fireEvent.click(methodControl(screen.getByRole('group', { name: 'Контакт 1' })));
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Телефон', 'Email', 'Telegram', 'WhatsApp', 'Другой мессенджер', 'VK', 'Другая соцсеть', 'Сайт', 'Другое',
    ]);
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
    expect(contacts.updateRow).toHaveBeenCalledWith('r1', { value: '7' });
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

  it('кнопки удаления имеют доступные имена и расположены в заголовке строки', () => {
    renderEditor(make({ rows: [row(), row({ id: 'r2' })] }));
    const [first, second] = screen.getAllByRole('group');
    expect(within(first).getByRole('button', { name: 'Удалить контакт 1' })).toBeInTheDocument();
    expect(within(second).getByRole('button', { name: 'Удалить контакт 2' })).toBeInTheDocument();
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
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить контакты' }));
    expect(contacts.save).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button', { name: 'Отменить изменения' }));
    expect(contacts.revert).toHaveBeenCalled();
  });

  it('без изменений кнопки сохранения и отмены отключены', () => {
    renderEditor(make({ rows: [row()] }));
    expect(screen.getByRole('button', { name: 'Сохранить контакты' })).toBeDisabled();
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
    expect(screen.getByRole('button', { name: 'Сохранить контакты' })).toBeDisabled();
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

const saveButton = () => screen.getByRole('button', { name: 'Сохранить контакты' });
const lastPayload = () => saveMyContacts.mock.calls[saveMyContacts.mock.calls.length - 1][0];

describe('ContactsEditor с реальным хуком', () => {
  beforeEach(() => {
    saveMyContacts.mockImplementation(async ({ version, items }) => ({
      ...snapshot(items, version + 1), changed: true,
    }));
  });

  it.each([
    ['Телефон', 'Номер телефона', '+79001234567', { type: 'phone', service: null }],
    ['Email', 'Email', 'me@example.org', { type: 'email', service: null }],
    ['Сайт', 'Адрес сайта', 'example.org', { type: 'website', service: null }],
    ['Telegram', 'Имя пользователя, номер или ссылка', '@my_name', { type: 'messenger', service: 'telegram' }],
    ['WhatsApp', 'Имя пользователя, номер или ссылка', '+79001234567', { type: 'messenger', service: 'whatsapp' }],
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
    expect(lastPayload().items[0]).toMatchObject({ type: 'phone', service: null, label: null });
  });

  it('«Другой мессенджер» без названия: ошибка у «Название», фокус на нём; с названием — сохраняется', async () => {
    await openConnected();
    const group = addContact();
    chooseMethod(group, 'Другой мессенджер');
    fireEvent.change(within(group).getByLabelText('Контакт или ссылка'), { target: { value: 'my-id' } });
    fireEvent.click(saveButton());

    const name = await within(group).findByLabelText('Название');
    expect(name).toHaveFocus();
    expect(name).toHaveAttribute('aria-invalid', 'true');
    expect(saveMyContacts).not.toHaveBeenCalled();

    fireEvent.change(name, { target: { value: 'Мой сервис' } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(saveMyContacts).toHaveBeenCalledTimes(1));
    expect(lastPayload().items[0]).toMatchObject({
      type: 'messenger', service: 'other', value: 'my-id', label: 'Мой сервис',
    });
  });

  it('тип «Другое» требует «Название»; «Другая соцсеть» — тоже', async () => {
    await openConnected();
    const first = addContact();
    chooseMethod(first, 'Другое');
    fireEvent.change(within(first).getByLabelText('Контакт'), { target: { value: 'в кабинете 5' } });
    fireEvent.click(saveButton());
    expect(await within(first).findByLabelText('Название')).toHaveAttribute('aria-invalid', 'true');
    expect(saveMyContacts).not.toHaveBeenCalled();

    const second = addContact();
    chooseMethod(second, 'Другая соцсеть');
    expect(within(second).getByLabelText('Название')).toBeInTheDocument();
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
        type: 'phone', service: null, value: '+79001112233', label: 'рабочий',
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
      items: [{ id, type: 'phone', service: null, value: '+79001112233', label: null }],
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
    expect(within(group).getByLabelText('Номер телефона')).toHaveValue('+79001112233');
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
    expect(lastPayload().items[0].value).toBe('+79001112233');
  });
});
