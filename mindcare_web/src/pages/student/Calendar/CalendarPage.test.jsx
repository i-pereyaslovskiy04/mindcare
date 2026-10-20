import fs from 'fs';
import path from 'path';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import CalendarPage from './CalendarPage';
import { MONTH_NAMES, MONTH_NAMES_GENITIVE } from './utils/calendarUtils';
import { useMyAppointments } from '../../../features/appointments/hooks/useMyAppointments';
import { getStudentMeetingTypes } from '../../../api/appointments.api';

jest.mock('../../../features/appointments/hooks/useMyAppointments', () => ({
  useMyAppointments: jest.fn(),
}));
jest.mock('../../../features/appointments/hooks/useAvailableSlots', () => ({
  useAvailableSlots: () => ({ slots: [], loading: false, error: null }),
}));
jest.mock('../../../api/appointments.api', () => ({
  getStudentMeetingTypes: jest.fn(),
  bookAppointment: jest.fn(),
  cancelAppointment: jest.fn(),
}));

// Календарь открывается на текущем месяце — данные строим от «сегодня».
// Полдень по местному времени: в МСК (как считает страница) та же дата.
const now = new Date();
const Y = now.getFullYear();
const M = now.getMonth();
const D = now.getDate();
const atNoon = (day) => new Date(Y, M, day, 12, 0).toISOString();

// Сценарии формы записи — в следующем месяце: все его дни заведомо будущие.
const NY = M === 11 ? Y + 1 : Y;
const NM = (M + 1) % 12;
const pad = (n) => String(n).padStart(2, '0');
const nextDayName = (d) => new RegExp(`^${d} ${MONTH_NAMES_GENITIVE[NM]}`);
const nextDisplay = (d) => `${pad(d)}.${pad(NM + 1)}.${NY}`;

const nextMonthSession = {
  uuid: 'appt-next',
  starts_at: new Date(NY, NM, 16, 12, 0).toISOString(),
  ends_at: null,
  status: 'pending_confirmation',
  meeting_type_name: 'Консультация в следующем месяце',
  psychologist: { full_name: 'Мария Ковалёва' },
  modality: 'online',
  topic: '',
};

const todaySession = {
  uuid: 'appt-today',
  starts_at: atNoon(D),
  ends_at: null,
  status: 'pending_confirmation',
  meeting_type_name: 'Индивидуальная консультация',
  psychologist: { full_name: 'Мария Ковалёва' },
  modality: 'online',
  topic: '',
};

function renderPage(items = [todaySession]) {
  useMyAppointments.mockReturnValue({ items, loading: false, refetch: jest.fn() });
  return render(<CalendarPage />);
}

const todayButtonName = new RegExp(`^${D} ${MONTH_NAMES_GENITIVE[M]}`);

// Предмет проверки — связь aria-controls → окно (у окна нет своей роли).
function popupOf(dayButton) {
  // eslint-disable-next-line testing-library/no-node-access
  return document.getElementById(dayButton.getAttribute('aria-controls'));
}
// Поле «Дата» формы записи (DateInput): имя — подпись «Дата» + показанная дата.
const dateField = (text) => screen.getByRole('button', { name: `Дата ${text}` });

async function renderInNextMonth(items = [nextMonthSession]) {
  renderPage(items);
  await waitFor(() => expect(getStudentMeetingTypes).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: 'Следующий месяц' }));
}

beforeEach(() => {
  getStudentMeetingTypes.mockResolvedValue([]);
});

test('показывает текущий месяц и год; prev/next меняют месяц', async () => {
  renderPage([]);
  await waitFor(() => expect(getStudentMeetingTypes).toHaveBeenCalled());
  expect(screen.getByText(MONTH_NAMES[M])).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Следующий месяц' }));
  expect(screen.getByText(MONTH_NAMES[(M + 1) % 12])).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Предыдущий месяц' }));
  fireEvent.click(screen.getByRole('button', { name: 'Предыдущий месяц' }));
  expect(screen.getByText(MONTH_NAMES[(M + 11) % 12])).toBeInTheDocument();
});

test('сессия из API — день-кнопка «сегодня», окно показывает её данные', async () => {
  renderPage();
  await waitFor(() => expect(getStudentMeetingTypes).toHaveBeenCalled());

  const day = screen.getByRole('button', { name: todayButtonName });
  expect(day).toHaveAttribute('aria-current', 'date');
  expect(day).toHaveAttribute('aria-expanded', 'false');

  fireEvent.click(day);
  expect(day).toHaveAttribute('aria-expanded', 'true');
  const popup = popupOf(day);
  expect(popup).not.toBeNull();
  expect(within(popup).getByText('События дня')).toBeInTheDocument();
  expect(within(popup).getByText('Индивидуальная консультация')).toBeInTheDocument();
});

test('день с сессией: кнопка, окно с записью, дата уходит в форму', async () => {
  await renderInNextMonth();
  expect(dateField('Выберите дату')).toBeInTheDocument();

  const day = screen.getByRole('button', { name: nextDayName(16) });
  expect(day).toHaveAccessibleName(expect.stringContaining('есть события'));
  fireEvent.click(day);

  const popup = popupOf(day);
  expect(within(popup).getByText('Консультация в следующем месяце')).toBeInTheDocument();
  expect(dateField(nextDisplay(16))).toBeInTheDocument();
  expect(day).toHaveClass('active');
});

test('пустой день месяца: кнопка, окно «На этот день записей нет», дата в форме', async () => {
  await renderInNextMonth();
  const day = screen.getByRole('button', { name: nextDayName(20) });
  expect(day.tagName).toBe('BUTTON');
  fireEvent.click(day);

  expect(day).toHaveAttribute('aria-expanded', 'true');
  expect(within(popupOf(day)).getByText('На этот день записей нет')).toBeInTheDocument();
  expect(dateField(nextDisplay(20))).toBeInTheDocument();
});

test('другая дата: выбор, окно и поле формы переходят на неё', async () => {
  await renderInNextMonth();
  const first = screen.getByRole('button', { name: nextDayName(16) });
  const second = screen.getByRole('button', { name: nextDayName(20) });

  fireEvent.click(first);
  expect(dateField(nextDisplay(16))).toBeInTheDocument();

  fireEvent.click(second);
  expect(dateField(nextDisplay(20))).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: `Дата ${nextDisplay(16)}` })).toBeNull();
  expect(first).not.toHaveClass('active');
  expect(first).toHaveAttribute('aria-expanded', 'false');
  expect(second).toHaveClass('active');
  // Окно одно, и в нём данные новой даты.
  expect(screen.getAllByText('События дня')).toHaveLength(1);
  const popup = popupOf(second);
  expect(within(popup).getByText('На этот день записей нет')).toBeInTheDocument();
  // Сессия 16-го остаётся в списке «Предстоящие», но не в окне 20-го.
  expect(within(popup).queryByText('Консультация в следующем месяце')).toBeNull();
});

test('повторное нажатие выбранного дня закрывает окно, дата в форме остаётся', async () => {
  await renderInNextMonth();
  const day = screen.getByRole('button', { name: nextDayName(20) });
  fireEvent.click(day);
  fireEvent.click(day);
  expect(screen.queryByText('События дня')).toBeNull();
  expect(day).toHaveAttribute('aria-expanded', 'false');
  expect(day).toHaveClass('active');
  expect(dateField(nextDisplay(20))).toBeInTheDocument();
});

test('смена месяца закрывает окно; выбранная дата формы не теряется', async () => {
  await renderInNextMonth();
  fireEvent.click(screen.getByRole('button', { name: nextDayName(16) }));
  expect(screen.getByText('События дня')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Следующий месяц' }));
  expect(screen.queryByText('События дня')).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'Предыдущий месяц' }));
  expect(screen.queryByText('События дня')).toBeNull();
  const day = screen.getByRole('button', { name: nextDayName(16) });
  expect(day).toHaveAttribute('aria-expanded', 'false');
  expect(day).toHaveClass('active');
  expect(dateField(nextDisplay(16))).toBeInTheDocument();
});

test('прошедший день открывает окно, но не подставляет дату в форму', async () => {
  renderPage([]);
  await waitFor(() => expect(getStudentMeetingTypes).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: 'Предыдущий месяц' }));
  const PM = (M + 11) % 12;
  const day = screen.getByRole('button', { name: new RegExp(`^10 ${MONTH_NAMES_GENITIVE[PM]}`) });

  fireEvent.click(day);
  expect(within(popupOf(day)).getByText('На этот день записей нет')).toBeInTheDocument();
  expect(dateField('Выберите дату')).toBeInTheDocument();
});

test('ручной выбор в DateInput подсвечивает день в календаре и закрывает окно', async () => {
  renderPage([]);
  await waitFor(() => expect(getStudentMeetingTypes).toHaveBeenCalled());
  // Окно другого дня, открытое до ручного выбора, должно закрыться.
  const otherDay = D === 1 ? 2 : 1;
  fireEvent.click(screen.getByRole('button', {
    name: new RegExp(`^${otherDay} ${MONTH_NAMES_GENITIVE[M]}`),
  }));
  expect(screen.getByText('События дня')).toBeInTheDocument();

  fireEvent.click(dateField('Выберите дату'));
  const panel = screen.getByRole('dialog', { name: 'Выбор даты' });
  fireEvent.click(within(panel).getByRole('button', { name: String(D) }));

  expect(dateField(`${pad(D)}.${pad(M + 1)}.${Y}`)).toBeInTheDocument();
  expect(screen.queryByText('События дня')).toBeNull();
  const today = screen.getByRole('button', { name: todayButtonName });
  expect(today).toHaveClass('active');
  expect(today).toHaveAccessibleName(expect.stringMatching(/выбрано$/));
});

test('«✕» и Escape закрывают окно и возвращают фокус на кнопку дня', async () => {
  renderPage();
  await waitFor(() => expect(getStudentMeetingTypes).toHaveBeenCalled());
  const day = screen.getByRole('button', { name: todayButtonName });

  fireEvent.click(day);
  fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
  expect(screen.queryByText('События дня')).toBeNull();
  expect(day).toHaveFocus();

  fireEvent.click(day);
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(screen.queryByText('События дня')).toBeNull();
  expect(day).toHaveFocus();
});

test('видимая подпись «Дата» связана с полем даты формы записи', async () => {
  renderPage([]);
  await waitFor(() => expect(getStudentMeetingTypes).toHaveBeenCalled());
  const field = screen.getByRole('button', { name: /^Дата/ });
  expect(field).toHaveAccessibleName('Дата Выберите дату');
  expect(field).toHaveAttribute('aria-haspopup', 'dialog');
});

test('порядок блоков: календарь → форма записи → предстоящие → история', async () => {
  const pastSession = {
    ...todaySession,
    uuid: 'appt-past',
    starts_at: new Date(Y, M - 1, 10, 12, 0).toISOString(),
    status: 'completed',
  };
  renderPage([nextMonthSession, pastSession]);
  await waitFor(() => expect(getStudentMeetingTypes).toHaveBeenCalled());

  // На телефоне блоки идут в порядке DOM (grid-areas меняют только desktop).
  const order = [
    screen.getByRole('button', { name: 'Следующий месяц' }),
    screen.getByRole('heading', { name: 'Записаться на сессию' }),
    screen.getByRole('heading', { name: 'Предстоящие сессии' }),
    screen.getByRole('heading', { name: /^История сессий/ }),
  ];
  for (let i = 1; i < order.length; i += 1) {
    expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING)
      .toBeTruthy();
  }
});

describe('предстоящие и прошедшие записи', () => {
  const prevMonth = (day) => new Date(Y, M - 1, day, 12, 0).toISOString();
  const pastPending = {
    ...todaySession, uuid: 'past-pending', starts_at: prevMonth(10),
    status: 'pending_confirmation', meeting_type_name: 'Прошлая ожидающая',
  };
  const futurePending = {
    ...nextMonthSession, uuid: 'future-pending', meeting_type_name: 'Будущая ожидающая',
  };
  const pastConfirmed = {
    ...todaySession, uuid: 'past-confirmed', starts_at: prevMonth(12),
    status: 'confirmed', meeting_type_name: 'Прошлая подтверждённая',
  };

  // История свёрнута: видимый список до раскрытия — только «Предстоящие».
  const upcomingList = () => screen.getByRole('list');
  function openHistory() {
    const toggle = screen.getByRole('button', { name: /^История сессий/ });
    fireEvent.click(toggle);
    // eslint-disable-next-line testing-library/no-node-access
    return document.getElementById(toggle.getAttribute('aria-controls'));
  }

  test('прошедшая pending_confirmation — в истории, без «Отменить» и без итога', async () => {
    renderPage([pastPending, futurePending]);
    await waitFor(() => expect(getStudentMeetingTypes).toHaveBeenCalled());

    expect(within(upcomingList()).queryByText('Прошлая ожидающая')).toBeNull();

    const history = openHistory();
    const item = within(history).getByText('Прошлая ожидающая').closest('li'); // eslint-disable-line testing-library/no-node-access
    expect(within(item).queryByRole('button')).toBeNull();
    expect(within(item).queryByText('Ожидает подтверждения')).toBeNull();
    expect(within(item).queryByText('Состоялась')).toBeNull();
  });

  test('будущая pending_confirmation — в «Предстоящих», отмена доступна', async () => {
    renderPage([pastPending, futurePending]);
    await waitFor(() => expect(getStudentMeetingTypes).toHaveBeenCalled());

    const upcoming = upcomingList();
    expect(within(upcoming).getByText('Будущая ожидающая')).toBeInTheDocument();
    expect(within(upcoming).getByText('Ожидает подтверждения')).toBeInTheDocument();
    expect(within(upcoming).getByRole('button', { name: 'Отменить' })).toBeInTheDocument();
    // Единственная «Отменить» на странице — у будущей записи.
    expect(screen.getAllByRole('button', { name: 'Отменить' })).toHaveLength(1);
  });

  test('прошедшая confirmed — в истории, без ложного «Состоялась»', async () => {
    renderPage([pastConfirmed]);
    await waitFor(() => expect(getStudentMeetingTypes).toHaveBeenCalled());

    // Будущих нет — блока «Предстоящие» нет.
    expect(screen.queryByRole('heading', { name: 'Предстоящие сессии' })).toBeNull();
    const history = openHistory();
    expect(within(history).getByText('Прошлая подтверждённая')).toBeInTheDocument();
    expect(within(history).queryByText('Состоялась')).toBeNull();
    expect(within(history).queryByText('Подтверждена')).toBeNull();
    expect(within(history).queryByRole('button')).toBeNull();
  });
});

test('без сессий нет дней с событиями: mock-задания и дневник не подмешиваются', async () => {
  renderPage([]);
  await waitFor(() => expect(getStudentMeetingTypes).toHaveBeenCalled());
  expect(screen.queryAllByRole('button', { name: /есть события/ })).toHaveLength(0);
  // Легенда — только реальные типы.
  expect(screen.getByText('Сессия')).toBeInTheDocument();
  expect(screen.queryByText('Задание')).toBeNull();
  expect(screen.queryByText('Запись в дневнике')).toBeNull();
});

test('mock-события удалены из исходников календаря', () => {
  const page = fs.readFileSync(path.join(__dirname, 'CalendarPage.jsx'), 'utf8');
  expect(page).not.toMatch(/mockEvents|MOCK_EVENTS/);
  expect(fs.existsSync(path.join(__dirname, 'data', 'mockEvents.js'))).toBe(false);
});
