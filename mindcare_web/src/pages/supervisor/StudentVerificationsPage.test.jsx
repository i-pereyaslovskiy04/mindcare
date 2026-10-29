import { act, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import StudentVerificationsPage from './StudentVerificationsPage';
import { useAuth } from '../../features/auth/AuthContext';
import * as api from '../../api/studentVerification.api';
import { VERIFICATIONS_CHANGED_EVENT } from '../../features/studentVerification/lib/verificationEvents';

jest.mock('../../features/auth/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../api/studentVerification.api');

const UUID = '1b4e28ba-2fa1-11d2-883f-0016d3cca427';
const ITEM = {
  uuid: UUID,
  status: 'pending',
  faculty: { code: 'law', label: 'Юридический факультет' },
  submitted_at: '2026-10-01T09:00:00Z',
  reviewed_at: null,
  student: { uuid: 'u-1', full_name: 'Иван Тестов', email: 'ivan@donnu.ru', is_active: true },
  reviewer: null,
};

function historyItem(uuid, status, events, extra = {}) {
  return {
    uuid, status, is_current: false,
    faculty: { code: 'law', label: 'Юридический факультет' },
    events, ...extra,
  };
}

const CURRENT_HISTORY = historyItem(UUID, 'pending', [
  { type: 'resubmitted', at: '2026-10-01T09:00:00Z', actor: { full_name: 'Иван Тестов' }, reason: null },
], { is_current: true });

const CARD = {
  ...ITEM,
  ticket_number: '000123',
  rejection_reason: null,
  can_review: true,
  history: { items: [CURRENT_HISTORY], has_more: false, next_cursor: null },
};

function many(n, offset = 0) {
  return Array.from({ length: n }, (_, i) => ({
    ...ITEM,
    uuid: `00000000-0000-0000-0000-${String(offset + i).padStart(12, '0')}`,
    student: { ...ITEM.student, full_name: `Пользователь ${offset + i}` },
  }));
}

function error(code, message = 'Ошибка') {
  const err = new Error(message);
  err.code = code;
  return err;
}

// jsdom не применяет CSS: ResponsiveTable держит в DOM обе раскладки очереди
// (таблицу и список). Строки ищем в таблице; отсутствие проверяем по всему DOM.
const QUEUE = 'Заявки на подтверждение статуса студента';
const queue = () => within(screen.getByRole('table', { name: QUEUE }));
const findQueue = async () => within(await screen.findByRole('table', { name: QUEUE }));

let changedEvents = 0;
const onChanged = () => { changedEvents += 1; };

beforeEach(() => {
  jest.clearAllMocks();
  changedEvents = 0;
  window.addEventListener(VERIFICATIONS_CHANGED_EVENT, onChanged);
  useAuth.mockReturnValue({ isImpersonating: false });
  api.getStudentVerifications.mockResolvedValue({ items: [ITEM], total: 1, page: 1, size: 20 });
  api.getStudentVerification.mockResolvedValue(CARD);
  api.approveStudentVerification.mockResolvedValue({ ...ITEM, status: 'approved' });
  api.rejectStudentVerification.mockResolvedValue({ ...ITEM, status: 'rejected' });
});

afterEach(() => {
  window.removeEventListener(VERIFICATIONS_CHANGED_EVENT, onChanged);
});

async function openCard() {
  render(<StudentVerificationsPage />);
  fireEvent.click((await findQueue()).getByRole('button', { name: /Открыть заявку: Иван Тестов/ }));
  return screen.findByRole('dialog', { name: 'Заявка на подтверждение студента' });
}

// ── очередь ──────────────────────────────────────────────────────────────────

test('очередь: только pending без поиска, фильтров и строки поиска нет, номера нет', async () => {
  render(<StudentVerificationsPage />);
  expect((await findQueue()).getByText('Иван Тестов')).toBeInTheDocument();
  expect(api.getStudentVerifications).toHaveBeenCalledWith({ page: 1, size: 20, status: 'pending' });
  expect(screen.queryByRole('searchbox')).toBeNull();
  expect(screen.queryByRole('group', { name: 'Статус заявки' })).toBeNull();
  for (const name of ['На проверке', 'Подтверждено', 'Отклонено', 'Все']) {
    expect(screen.queryByRole('button', { name })).toBeNull();
  }
  expect(screen.queryByText('000123')).toBeNull();
  expect(screen.getByText(/Ожидают проверки:/)).toHaveTextContent('Ожидают проверки: 1');
  // Декоративной подписи роли над заголовком нет.
  expect(screen.queryByText('Супервизия')).toBeNull();
  expect(screen.getByRole('heading', { level: 1, name: 'Подтверждение студентов' })).toBeInTheDocument();
});

test('серверная пагинация по 20: диапазон «1–20 из 45» и переход на следующую страницу', async () => {
  api.getStudentVerifications.mockImplementation(({ page }) => Promise.resolve(
    page === 1 ? { items: many(20), total: 45 } : { items: many(20, 20), total: 45 },
  ));
  render(<StudentVerificationsPage />);
  expect(await screen.findByText('1–20 из 45')).toBeInTheDocument();
  expect(screen.getByText('Страница 1 из 3')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
  expect(await screen.findByText('21–40 из 45')).toBeInTheDocument();
  expect(api.getStudentVerifications).toHaveBeenLastCalledWith({ page: 2, size: 20, status: 'pending' });
});

test('пустая очередь — понятное сообщение без диапазона', async () => {
  api.getStudentVerifications.mockResolvedValue({ items: [], total: 0 });
  render(<StudentVerificationsPage />);
  expect(await screen.findByText('Заявок на проверке нет')).toBeInTheDocument();
  expect(screen.getByText(/Ожидают проверки:/)).toHaveTextContent('Ожидают проверки: 0');
});

async function goToPage3(total) {
  api.getStudentVerifications.mockImplementation(({ page }) => Promise.resolve(
    { items: many(page === 3 ? 1 : 20, (page - 1) * 20), total },
  ));
  render(<StudentVerificationsPage />);
  await screen.findByText(`1–20 из ${total}`);
  fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
  await screen.findByText(`21–40 из ${total}`);
  fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
  await screen.findByText(`41–41 из ${total}`);
}

test('опустевшая последняя страница после решения → последняя существующая', async () => {
  await goToPage3(41);
  api.getStudentVerifications.mockImplementation(({ page }) => Promise.resolve(
    page === 3 ? { items: [], total: 40 } : { items: many(20, 20), total: 40 },
  ));
  api.getStudentVerification.mockResolvedValue({ ...CARD, uuid: many(1, 40)[0].uuid });
  fireEvent.click(queue().getByRole('button', { name: /Открыть заявку: Пользователь 40/ }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Подтвердить' }));
  expect(await screen.findByText('21–40 из 40')).toBeInTheDocument();
  expect(api.getStudentVerifications).toHaveBeenLastCalledWith({ page: 2, size: 20, status: 'pending' });
  expect(changedEvents).toBeGreaterThanOrEqual(1);
});

test('все записи исчезли на странице > 1 (total=0) → страница 1', async () => {
  await goToPage3(41);
  api.getStudentVerifications.mockResolvedValue({ items: [], total: 0 });
  fireEvent.click(queue().getByRole('button', { name: /Открыть заявку: Пользователь 40/ }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Подтвердить' }));
  expect(await screen.findByText('Заявок на проверке нет')).toBeInTheDocument();
  expect(api.getStudentVerifications).toHaveBeenLastCalledWith({ page: 1, size: 20, status: 'pending' });
});

// ── решения ──────────────────────────────────────────────────────────────────

test('«Подтвердить»: решение, обновление очереди и сигнал для счётчика меню', async () => {
  const dialog = await openCard();
  expect(await within(dialog).findByText('000123')).toBeInTheDocument();
  expect(api.getStudentVerification).toHaveBeenCalledWith(UUID);
  fireEvent.click(within(dialog).getByRole('button', { name: 'Подтвердить' }));
  await waitFor(() => expect(api.approveStudentVerification).toHaveBeenCalledWith(UUID));
  await waitFor(() => expect(api.getStudentVerifications).toHaveBeenCalledTimes(2));
  expect(changedEvents).toBe(1);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
});

test('отказ требует пояснения и отправляет его без пробелов по краям', async () => {
  const dialog = await openCard();
  await within(dialog).findByText('000123');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Отклонить' }));
  fireEvent.click(within(dialog).getByRole('button', { name: 'Отклонить заявку' }));
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Укажите пояснение отказа');
  expect(api.rejectStudentVerification).not.toHaveBeenCalled();

  fireEvent.change(within(dialog).getByLabelText(/Пояснение отказа/), {
    target: { value: '  Номер не совпадает  ' },
  });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Отклонить заявку' }));
  await waitFor(() => expect(api.rejectStudentVerification)
    .toHaveBeenCalledWith(UUID, 'Номер не совпадает'));
});

test('собственная заявка: кнопок решения нет, показано пояснение', async () => {
  api.getStudentVerification.mockResolvedValue({ ...CARD, can_review: false });
  const dialog = await openCard();
  expect(await within(dialog).findByText('Нельзя проверять собственную заявку.'))
    .toBeInTheDocument();
  expect(within(dialog).queryByRole('button', { name: 'Подтвердить' })).toBeNull();
  expect(within(dialog).queryByRole('button', { name: 'Отклонить' })).toBeNull();
});

test.each([
  ['verification_already_decided', 'По заявке уже принято другое решение.'],
  ['verification_not_found', 'Заявка не найдена.'],
])('конкурентное решение (%s): текст, кнопки скрыты, очередь и счётчик обновлены', async (code, text) => {
  api.approveStudentVerification.mockRejectedValue(error(code, 'raw backend text'));
  const dialog = await openCard();
  await within(dialog).findByText('000123');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Подтвердить' }));
  expect(await within(dialog).findByRole('alert')).toHaveTextContent(text);
  expect(within(dialog).queryByRole('button', { name: 'Подтвердить' })).toBeNull();
  expect(within(dialog).queryByRole('button', { name: 'Отклонить' })).toBeNull();
  // Остаётся только «Закрыть» (кнопка действия и крестик модалки).
  expect(within(dialog).getAllByRole('button', { name: 'Закрыть' }).length).toBeGreaterThanOrEqual(1);
  await waitFor(() => expect(api.getStudentVerifications).toHaveBeenCalledTimes(2));
  expect(changedEvents).toBe(1);
});

test('прочая ошибка решения не скрывает кнопки', async () => {
  api.approveStudentVerification.mockRejectedValue(error('reviewer_not_allowed'));
  const dialog = await openCard();
  await within(dialog).findByText('000123');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Подтвердить' }));
  expect(await within(dialog).findByRole('alert'))
    .toHaveTextContent('Недостаточно прав для проверки заявок.');
  expect(within(dialog).getByRole('button', { name: 'Подтвердить' })).toBeInTheDocument();
  expect(changedEvents).toBe(0);
});

test('сбой аудита чтения (503): ни номера, ни истории, выводится сообщение', async () => {
  api.getStudentVerification.mockRejectedValue(
    error(undefined, 'Не удалось зафиксировать обращение к данным заявки. Повторите попытку.'),
  );
  const dialog = await openCard();
  expect(await within(dialog).findByRole('alert'))
    .toHaveTextContent('Не удалось зафиксировать обращение');
  expect(within(dialog).queryByText('000123')).toBeNull();
  expect(within(dialog).queryByText('История подтверждения')).toBeNull();
});

test('в режиме «под именем» раздел недоступен и запросов нет', async () => {
  useAuth.mockReturnValue({ isImpersonating: true });
  render(<StudentVerificationsPage />);
  expect(await screen.findByText(/недоступна при входе под именем/)).toBeInTheDocument();
  expect(api.getStudentVerifications).not.toHaveBeenCalled();
});

// ── история ──────────────────────────────────────────────────────────────────

const OLD_REJECTED = historyItem('old-2', 'rejected', [
  { type: 'rejected', at: '2026-09-20T12:00:00Z', actor: null, reason: 'Причина B' },
  { type: 'resubmitted', at: '2026-09-15T09:00:00Z', actor: { full_name: 'Иван Тестов' }, reason: null },
]);
const FIRST_REJECTED = historyItem('old-1', 'rejected', [
  { type: 'rejected', at: '2026-09-10T12:00:00Z', actor: { full_name: 'Пётр Супервизоров' }, reason: 'Причина A' },
  { type: 'submitted', at: '2026-09-01T09:00:00Z', actor: { full_name: 'Иван Тестов' }, reason: null },
]);

test('история: события с датой, исполнителем, причинами; недоступный проверявший; текущая заявка', async () => {
  api.getStudentVerification.mockResolvedValue({
    ...CARD,
    history: { items: [CURRENT_HISTORY, OLD_REJECTED, FIRST_REJECTED], has_more: false, next_cursor: null },
  });
  const dialog = await openCard();
  const history = await within(dialog).findByRole('region', { name: 'История подтверждения' });
  const events = within(history).getAllByRole('listitem');
  expect(events.map((li) => within(li).getAllByText(/Заявка|Статус/)[0].textContent)).toEqual([
    'Заявка подана повторно', 'Заявка отклонена', 'Заявка подана повторно',
    'Заявка отклонена', 'Заявка подана',
  ]);
  expect(within(events[0]).getByText('текущая заявка')).toBeInTheDocument();
  expect(within(events[1]).getByText('Сведения о проверявшем недоступны')).toBeInTheDocument();
  expect(within(events[1]).getByText(/Причина B/)).toBeInTheDocument();
  expect(within(events[3]).getByText('Проверил(а): Пётр Супервизоров')).toBeInTheDocument();
  expect(within(events[3]).getByText(/Причина A/)).toBeInTheDocument();
  expect(within(events[4]).getByText('Заявитель: Иван Тестов')).toBeInTheDocument();
  expect(within(history).queryByRole('button', { name: 'Показать ещё' })).toBeNull();
});

test('история: одобрение без причины', async () => {
  api.getStudentVerification.mockResolvedValue({
    ...CARD,
    status: 'approved',
    can_review: false,
    history: {
      items: [historyItem(UUID, 'approved', [
        { type: 'approved', at: '2026-10-02T10:00:00Z', actor: { full_name: 'Пётр Супервизоров' }, reason: null },
        { type: 'submitted', at: '2026-10-01T09:00:00Z', actor: { full_name: 'Иван Тестов' }, reason: null },
      ], { is_current: true })],
      has_more: false,
      next_cursor: null,
    },
  });
  const dialog = await openCard();
  const history = await within(dialog).findByRole('region', { name: 'История подтверждения' });
  expect(within(history).getByText('Статус подтверждён')).toBeInTheDocument();
  expect(within(history).queryByText(/Причина отказа/)).toBeNull();
});

test('«Показать ещё»: следующая порция по курсору, без дублей, кнопка исчезает в конце', async () => {
  api.getStudentVerification.mockResolvedValue({
    ...CARD,
    history: { items: [CURRENT_HISTORY, OLD_REJECTED], has_more: true, next_cursor: 'old-2' },
  });
  api.getStudentVerificationHistory.mockResolvedValue({
    // Дубль old-2 (страховка клиента) + более ранняя заявка.
    items: [OLD_REJECTED, FIRST_REJECTED], has_more: false, next_cursor: null,
  });
  const dialog = await openCard();
  const history = await within(dialog).findByRole('region', { name: 'История подтверждения' });
  expect(within(history).getAllByRole('listitem')).toHaveLength(3);
  fireEvent.click(within(history).getByRole('button', { name: 'Показать ещё' }));
  await waitFor(() => expect(within(history).getAllByRole('listitem')).toHaveLength(5));
  expect(api.getStudentVerificationHistory).toHaveBeenCalledWith(UUID, { before: 'old-2', size: 10 });
  expect(within(history).getByText(/Причина A/)).toBeInTheDocument();
  expect(within(history).queryByRole('button', { name: 'Показать ещё' })).toBeNull();
});


// ── рассогласование страницы и строк (регрессия) ──────────────────────────────
// page меняется сразу, ответ приходит позже: до ответа нельзя показывать строки
// и диапазон прежней страницы и открывать её заявки как записи новой.

/** Ответы сервера задерживаются: каждый вызов — отдельный отложенный Promise. */
function deferredServer() {
  const calls = [];
  api.getStudentVerifications.mockImplementation(({ page }) => new Promise((resolve, reject) => {
    calls.push({
      page,
      respond: (items, total) => act(async () => { resolve({ items, total }); }),
      fail: (err) => act(async () => { reject(err); }),
    });
  }));
  return calls;
}

const next = () => screen.getByRole('button', { name: 'Далее' });
const prev = () => screen.getByRole('button', { name: 'Назад' });
const openButtons = () => screen.queryAllByRole('button', { name: /Открыть заявку/ });

function expectNoStaleView(oldRange, oldRow) {
  expect(screen.getByRole('status')).toHaveTextContent('Загрузка заявок…');
  expect(screen.queryByText(oldRange)).toBeNull();
  expect(screen.queryAllByText(oldRow)).toHaveLength(0);
  expect(screen.queryByText(/Ожидают проверки:/)).toBeNull();
  expect(openButtons()).toHaveLength(0);               // открыть старую заявку нельзя
  expect(next()).toBeDisabled();
  expect(prev()).toBeDisabled();
}

async function loadFirstPage(calls, total = 45) {
  render(<StudentVerificationsPage />);
  await waitFor(() => expect(calls).toHaveLength(1));
  await calls[0].respond(many(20), total);
  expect(await screen.findByText(`1–20 из ${total}`)).toBeInTheDocument();
}

test('«Далее»: пока страница 2 грузится, строки и диапазон страницы 1 недоступны', async () => {
  const calls = deferredServer();
  await loadFirstPage(calls);
  expect(queue().getByRole('button', { name: 'Открыть заявку: Пользователь 0' })).toBeInTheDocument();

  fireEvent.click(next());
  await waitFor(() => expect(calls).toHaveLength(2));
  expect(calls[1].page).toBe(2);
  expectNoStaleView('1–20 из 45', 'Пользователь 0');
  expect(screen.queryByText('21–40 из 45')).toBeNull();     // диапазона новой страницы тоже нет

  await calls[1].respond(many(20, 20), 45);
  expect(await screen.findByText('21–40 из 45')).toBeInTheDocument();
  expect(screen.getByText('Страница 2 из 3')).toBeInTheDocument();
  expect(queue().getByText('Пользователь 20')).toBeInTheDocument();
  expect(screen.queryAllByText('Пользователь 0')).toHaveLength(0);
  expect(queue().getAllByRole('button', { name: /Открыть заявку/ })).toHaveLength(20);
  expect(screen.queryByRole('status')).toBeNull();
  expect(next()).toBeEnabled();
  expect(prev()).toBeEnabled();
});

test('«Назад»: старые строки скрыты до ответа, затем показана предыдущая страница', async () => {
  const calls = deferredServer();
  await loadFirstPage(calls);
  fireEvent.click(next());
  await waitFor(() => expect(calls).toHaveLength(2));
  await calls[1].respond(many(20, 20), 45);
  await screen.findByText('21–40 из 45');

  fireEvent.click(prev());
  await waitFor(() => expect(calls).toHaveLength(3));
  expect(calls[2].page).toBe(1);
  expectNoStaleView('21–40 из 45', 'Пользователь 20');

  await calls[2].respond(many(20), 45);
  expect(await screen.findByText('1–20 из 45')).toBeInTheDocument();
  expect(queue().getByText('Пользователь 0')).toBeInTheDocument();
  expect(screen.queryAllByText('Пользователь 20')).toHaveLength(0);
});

test('ошибка загрузки новой страницы: ошибка вместо старых строк, вернуться «Назад» можно', async () => {
  const calls = deferredServer();
  await loadFirstPage(calls);
  fireEvent.click(next());
  await waitFor(() => expect(calls).toHaveLength(2));
  await calls[1].fail(new Error('Сервер недоступен'));

  expect(await screen.findByRole('alert')).toHaveTextContent('Сервер недоступен');
  expect(screen.queryAllByText('Пользователь 0')).toHaveLength(0);
  expect(openButtons()).toHaveLength(0);
  expect(prev()).toBeEnabled();

  fireEvent.click(prev());
  await waitFor(() => expect(calls).toHaveLength(3));
  expect(screen.queryByRole('alert')).toBeNull();             // ошибка принадлежала странице 2
  await calls[2].respond(many(20), 45);
  expect(await screen.findByText('1–20 из 45')).toBeInTheDocument();
});

async function reachPage3(calls) {
  await loadFirstPage(calls, 41);
  fireEvent.click(next());
  await waitFor(() => expect(calls).toHaveLength(2));
  await calls[1].respond(many(20, 20), 41);
  await screen.findByText('21–40 из 41');
  fireEvent.click(next());
  await waitFor(() => expect(calls).toHaveLength(3));
  await calls[2].respond(many(1, 40), 41);
  await screen.findByText('41–41 из 41');
}

async function decideRow40() {
  api.getStudentVerification.mockResolvedValue({ ...CARD, uuid: many(1, 40)[0].uuid });
  fireEvent.click(queue().getByRole('button', { name: 'Открыть заявку: Пользователь 40' }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Подтвердить' }));
  await waitFor(() => expect(api.approveStudentVerification).toHaveBeenCalled());
}

test('пустая последняя страница: пока грузится существующая, строки страницы 3 недоступны', async () => {
  const calls = deferredServer();
  await reachPage3(calls);
  await decideRow40();
  await waitFor(() => expect(calls).toHaveLength(4));        // refetch страницы 3
  expect(calls[3].page).toBe(3);

  await calls[3].respond([], 40);                           // страница 3 опустела
  await waitFor(() => expect(calls).toHaveLength(5));
  expect(calls[4].page).toBe(2);                            // коррекция → страница 2
  expectNoStaleView('41–41 из 41', 'Пользователь 40');
  expect(screen.queryByText('41–41 из 40')).toBeNull();

  await calls[4].respond(many(20, 20), 40);
  expect(await screen.findByText('21–40 из 40')).toBeInTheDocument();
  expect(screen.getByText('Страница 2 из 2')).toBeInTheDocument();
});

test('все заявки исчезли (total=0) на странице 3: загрузка страницы 1, затем пустая очередь', async () => {
  const calls = deferredServer();
  await reachPage3(calls);
  await decideRow40();
  await waitFor(() => expect(calls).toHaveLength(4));

  await calls[3].respond([], 0);
  await waitFor(() => expect(calls).toHaveLength(5));
  expect(calls[4].page).toBe(1);
  expect(screen.getByRole('status')).toHaveTextContent('Загрузка заявок…');
  expect(screen.queryAllByText('Пользователь 40')).toHaveLength(0);
  expect(screen.queryByText('Заявок на проверке нет')).toBeNull();

  await calls[4].respond([], 0);
  expect(await screen.findByText('Заявок на проверке нет')).toBeInTheDocument();
  expect(screen.getByText(/Ожидают проверки:/)).toHaveTextContent('Ожидают проверки: 0');
  expect(screen.queryByRole('status')).toBeNull();
});

// ── раскладка очереди: shared ResponsiveTable ────────────────────────────────

test('очередь на ResponsiveTable: колонки Пользователь, Факультет, Подана; одно действие «Открыть», без меню', async () => {
  render(<StudentVerificationsPage />);
  await findQueue();
  expect(queue().getAllByRole('columnheader').map((th) => th.textContent))
    .toEqual(['Пользователь', 'Факультет', 'Подана', 'Действия']);
  expect(queue().getByText('ivan@donnu.ru')).toBeInTheDocument();
  expect(queue().getByText('Юридический факультет')).toBeInTheDocument();

  const record = within(screen.getByRole('list', { name: QUEUE })).getByRole('listitem');
  expect(within(record).getByRole('heading', { name: 'Иван Тестов' })).toBeInTheDocument();
  expect(within(record).getByText('Юридический факультет')).toBeInTheDocument();
  expect(within(record).getByRole('term')).toHaveTextContent('Подана');
  expect(within(record).getByRole('button', { name: 'Открыть заявку: Иван Тестов' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Другие действия/ })).toBeNull();
});

test('«Открыть» из списка открывает ту же карточку (чтение — только при открытии)', async () => {
  render(<StudentVerificationsPage />);
  const list = within(await screen.findByRole('list', { name: QUEUE }));
  expect(api.getStudentVerification).not.toHaveBeenCalled();
  fireEvent.click(list.getByRole('button', { name: 'Открыть заявку: Иван Тестов' }));
  expect(await screen.findByRole('dialog', { name: 'Заявка на подтверждение студента' })).toBeInTheDocument();
  expect(api.getStudentVerification).toHaveBeenCalledTimes(1);
});

test('отключённый аккаунт помечен в обеих раскладках', async () => {
  api.getStudentVerifications.mockResolvedValue({
    items: [{ ...ITEM, student: { ...ITEM.student, is_active: false } }], total: 1,
  });
  render(<StudentVerificationsPage />);
  await findQueue();
  expect(screen.getAllByText('Аккаунт отключён')).toHaveLength(2);
});

test('своей responsive-механики у очереди нет — только ResponsiveTable', () => {
  const fs = jest.requireActual('fs');
  const path = jest.requireActual('path');
  const dir = path.join(__dirname, '../../features/studentVerification/ui');
  const css = fs.readFileSync(path.join(dir, 'VerificationsTable.module.css'), 'utf8');
  expect(css).not.toMatch(/@container|@media|container-type|<table|\.table\b/);
  const jsx = fs.readFileSync(path.join(dir, 'VerificationsTable.jsx'), 'utf8');
  expect(jsx).toMatch(/components\/UI\/ResponsiveTable\/ResponsiveTable/);
  expect(jsx).not.toMatch(/<table/);
});
