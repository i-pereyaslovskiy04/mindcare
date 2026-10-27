import fs from 'fs';
import path from 'path';
import { createRef } from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import CabinetHeader from './CabinetHeader';
import { resolveBreadcrumbs } from './breadcrumbs';
import { ThemeProvider } from '../../features/theme/ThemeContext';
import { A11yProvider } from '../../features/a11y/A11yContext';
import * as AuthContext from '../../features/auth/AuthContext';
import * as chatApi from '../../api/chat.api';

// react-router-dom (v7) не резолвится jest-резолвером — мокаем виртуально.
jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
  Link: ({ children, to, className, 'aria-label': ariaLabel, title, onClick }) => (
    <a href={to} className={className} aria-label={ariaLabel} title={title} onClick={onClick}>
      {children}
    </a>
  ),
}), { virtual: true });

jest.mock('../../api/chat.api');

const mockLogout = jest.fn();
jest.mock('../../features/auth/AuthContext', () => ({
  useAuth: jest.fn(),
  useLogout: () => mockLogout,
}));

const CRUMBS = [
  { label: 'Главная', to: '/student' },
  { label: 'Дневник состояния' },
];

function renderHeader(props = {}) {
  return render(
    <ThemeProvider>
      <A11yProvider>
        <CabinetHeader cabinetRole="student" breadcrumbs={CRUMBS} {...props} />
      </A11yProvider>
    </ThemeProvider>
  );
}

/** Рендер + ожидание первого ответа колокольчика (unread_count). */
async function renderHeaderReady(props = {}) {
  const utils = renderHeader(props);
  await waitFor(() => expect(chatApi.getSystemConversation).toHaveBeenCalled());
  return utils;
}

const root = () => document.documentElement;

/** a стоит в DOM раньше b. */
const expectBefore = (a, b) => {
  // eslint-disable-next-line no-bitwise
  expect(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
};

beforeEach(() => {
  jest.clearAllMocks();
  // По умолчанию ответ unread_count не приходит: тестам, не связанным с
  // колокольчиком, не нужны его асинхронные обновления. Тесты колокольчика
  // задают ответ явно.
  chatApi.getSystemConversation.mockReturnValue(new Promise(() => {}));
  chatApi.getSystemMessages.mockResolvedValue({ items: [] });
  AuthContext.useAuth.mockReturnValue({
    user: { name: 'Тест', roles: ['psychologist', 'student'] },
    setActiveRole: jest.fn(),
  });
});

afterEach(() => {
  localStorage.clear();
  ['data-theme', 'data-a11y', 'data-a11y-scheme', 'data-a11y-spacing', 'data-a11y-leading',
    'data-a11y-font', 'data-a11y-images'].forEach((a) => root().removeAttribute(a));
  root().style.removeProperty('--a11y-font-scale');
});

describe('CabinetHeader', () => {
  test('крошки — семантическая nav: «Главная» ссылка на корень кабинета, текущая — текст', () => {
    renderHeader();
    const nav = screen.getByRole('navigation', { name: 'Навигационная цепочка' });
    expect(within(nav).getAllByRole('listitem')).toHaveLength(2);

    const home = within(nav).getByRole('link', { name: 'Главная' });
    expect(home).toHaveAttribute('href', '/student');

    const current = within(nav).getByText('Дневник состояния');
    expect(current).toHaveAttribute('aria-current', 'page');
    expect(within(nav).queryByRole('link', { name: 'Дневник состояния' })).toBeNull();
  });

  test('на корне кабинета «Главная» — текущая страница, а не ссылка', () => {
    renderHeader({ breadcrumbs: [{ label: 'Главная' }] });
    const nav = screen.getByRole('navigation', { name: 'Навигационная цепочка' });
    expect(within(nav).queryByRole('link')).toBeNull();
    expect(within(nav).getByText('Главная')).toHaveAttribute('aria-current', 'page');
  });

  test('строгий порядок справа: поиск → уведомления → оформление → выход', async () => {
    await renderHeaderReady();
    const search = screen.getByRole('searchbox', { name: 'Поиск - будет доступен позже' });
    const bell = screen.getByRole('button', { name: 'Уведомления' });
    const appearance = screen.getByRole('button', { name: 'Оформление и версия для слабовидящих' });
    const logout = screen.getByRole('button', { name: 'Выйти' });

    expectBefore(search, bell);
    expectBefore(bell, appearance);
    expectBefore(appearance, logout);
  });

  test('нет кнопки почты, home-иконки и отдельной кнопки «глаз»', () => {
    renderHeader();
    expect(screen.queryByRole('button', { name: /Почта/i })).toBeNull();
    expect(screen.queryByRole('link', { name: 'На главную' })).toBeNull();
    expect(screen.queryAllByRole('link').filter((a) => a.getAttribute('href') === '/')).toHaveLength(0);
    // Версия для слабовидящих — только внутри панели «Оформление».
    expect(screen.queryByRole('button', { name: 'Версия для слабовидящих' })).toBeNull();
  });

  test('поиск — заглушка: поле выключено и не участвует в форме', () => {
    renderHeader();
    const search = screen.getByRole('searchbox', { name: 'Поиск - будет доступен позже' });
    expect(search).toBeDisabled();
    expect(search).toHaveAttribute('placeholder', 'Поиск по материалам, записям…');
    expect(search.form).toBeNull();
    expect(screen.getByTitle('Поиск будет доступен позже')).toContainElement(search);
  });

  test.each(['student', 'psychologist'])(
    '%s: рабочий колокольчик — badge из unread_count системной беседы',
    async (cabinetRole) => {
      chatApi.getSystemConversation.mockResolvedValue({
        conversation: { uuid: 'sys-1', type: 'system', last_message_at: null, unread_count: 4 },
      });
      await renderHeaderReady({ cabinetRole });
      const bell = await screen.findByRole('button', { name: 'Уведомления, новых: 4' });
      expect(bell).not.toHaveAttribute('aria-disabled');
      expect(bell).toHaveAttribute('aria-expanded', 'false');
      expect(within(bell).getByText('4')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Уведомления — скоро' })).toBeNull();
    },
  );

  test('без непрочитанных — колокольчик без badge и «точки»', async () => {
    chatApi.getSystemConversation.mockResolvedValue({ conversation: null });
    await renderHeaderReady();
    const bell = screen.getByRole('button', { name: 'Уведомления' });
    expect(bell.innerHTML).not.toMatch(/<span/);
  });

  test.each(['supervisor', 'admin'])(
    '%s: колокольчика и заглушки «Уведомления — скоро» нет, API не запрашивается',
    (cabinetRole) => {
      renderHeader({ cabinetRole });
      expect(screen.queryByRole('button', { name: /Уведомления/ })).toBeNull();
      expect(chatApi.getSystemConversation).not.toHaveBeenCalled();
      // Остальные кнопки на месте.
      expect(screen.getByRole('button', { name: 'Оформление и версия для слабовидящих' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Выйти' })).toBeInTheDocument();
    },
  );

  test('«Оформление» открывает одну панель: тема, палитра и существующий A11yToggle', () => {
    renderHeader();
    const trigger = screen.getByRole('button', { name: 'Оформление и версия для слабовидящих' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');

    const panel = screen.getByRole('dialog', { name: 'Оформление' });
    const appearance = within(panel).getByRole('group', { name: 'Оформление' });
    expect(within(appearance).getByRole('group', { name: 'Режим темы оформления' })).toBeInTheDocument();
    expect(within(appearance).getByRole('group', { name: 'Цветовая тема' })).toBeInTheDocument();

    const a11y = within(panel).getByRole('group', { name: 'Версия для слабовидящих' });
    const a11yBtn = within(a11y).getByRole('button', { name: 'Версия для слабовидящих' });
    expect(a11yBtn).toHaveAttribute('aria-pressed', 'false');
    // Контрастная палитра — не в обычном списке тем.
    expect(within(panel).queryByRole('button', { name: /Высококонтрастная/ })).toBeNull();
  });

  test('A11yToggle в панели включает версию для слабовидящих и закрывает панель', () => {
    renderHeader();
    const trigger = screen.getByRole('button', { name: 'Оформление и версия для слабовидящих' });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('button', { name: 'Версия для слабовидящих' }));

    expect(root().getAttribute('data-a11y')).toBe('on');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(trigger).toHaveFocus();

    // Повторное открытие — та же кнопка, теперь «Обычная версия».
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('button', { name: 'Обычная версия сайта' }));
    expect(root().hasAttribute('data-a11y')).toBe(false);
  });

  test('выбор режима темы в панели работает', () => {
    renderHeader();
    fireEvent.click(screen.getByRole('button', { name: 'Оформление и версия для слабовидящих' }));
    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }));
    expect(root().getAttribute('data-theme')).toBe('dongu-dark');
  });

  test('«Выйти» вызывает существующий logout', () => {
    renderHeader();
    fireEvent.click(screen.getByRole('button', { name: 'Выйти' }));
    expect(mockLogout).toHaveBeenCalledTimes(1);
  });

  test('CabinetSwitcher доступен в шапке (для свёрнутого sidebar)', () => {
    renderHeader({ cabinetRole: 'psychologist' });
    expect(screen.getByRole('button', { name: /Психолог/ })).toHaveAttribute('aria-expanded', 'false');
  });

  test('без onMenuOpen hamburger не рендерится', () => {
    renderHeader();
    expect(screen.queryByRole('button', { name: 'Открыть меню' })).toBeNull();
  });

  test('hamburger: слева от крошек, открывает меню, aria-expanded/controls, ref для фокуса', () => {
    const onMenuOpen = jest.fn();
    const ref = createRef();
    const { rerender } = renderHeader({ onMenuOpen, menuId: 'drawer-1', menuButtonRef: ref });

    const burger = screen.getByRole('button', { name: 'Открыть меню' });
    expectBefore(burger, screen.getByRole('navigation', { name: 'Навигационная цепочка' }));
    expect(burger).toHaveAttribute('aria-haspopup', 'dialog');
    expect(burger).toHaveAttribute('aria-expanded', 'false');
    expect(burger).not.toHaveAttribute('aria-controls');
    expect(ref.current).toBe(burger);

    fireEvent.click(burger);
    expect(onMenuOpen).toHaveBeenCalledTimes(1);

    rerender(
      <ThemeProvider>
        <A11yProvider>
          <CabinetHeader
            cabinetRole="student"
            breadcrumbs={CRUMBS}
            onMenuOpen={onMenuOpen}
            menuOpen
            menuId="drawer-1"
            menuButtonRef={ref}
          />
        </A11yProvider>
      </ThemeProvider>
    );
    expect(burger).toHaveAttribute('aria-expanded', 'true');
    expect(burger).toHaveAttribute('aria-controls', 'drawer-1');
  });

  test('мобильный порядок: hamburger → крошки → уведомления → оформление → выход', async () => {
    await renderHeaderReady({ onMenuOpen: jest.fn() });
    const order = [
      screen.getByRole('button', { name: 'Открыть меню' }),
      screen.getByRole('navigation', { name: 'Навигационная цепочка' }),
      screen.getByRole('button', { name: 'Уведомления' }),
      screen.getByRole('button', { name: 'Оформление и версия для слабовидящих' }),
      screen.getByRole('button', { name: 'Выйти' }),
    ];
    order.slice(1).forEach((el, i) => expectBefore(order[i], el));
  });
});

// Ширины jsdom не моделирует — проверяем сами responsive-правила CSS
// (визуальные брейкпоинты — ручной smoke).
describe('CabinetHeader.module.css: responsive-правила', () => {
  const css = fs.readFileSync(path.join(__dirname, 'CabinetHeader.module.css'), 'utf8');
  const mediaBlock = (width) => {
    const start = css.indexOf(`@media (max-width: ${width}px) {`);
    expect(start).toBeGreaterThanOrEqual(0);
    const next = css.indexOf('@media', start + 1);
    return css.slice(start, next === -1 ? undefined : next);
  };
  const hides = (block, cls) =>
    new RegExp(`\\.${cls}\\s*\\{[^}]*display:\\s*none`).test(block);

  test('<=980px: поиск-заглушка скрыта, switcher показан', () => {
    const block = mediaBlock(980);
    expect(hides(block, 'search')).toBe(true);
    expect(block).toMatch(/\.switcher\s*\{[^}]*display:\s*inline-flex/);
  });

  test('<=600px: hamburger показан, switcher уходит в drawer, колокольчик и выход не скрываются', () => {
    const block = mediaBlock(600);
    expect(block).toMatch(/\.menuBtn\s*\{[^}]*display:\s*inline-flex/);
    expect(hides(block, 'switcher')).toBe(true);
    expect(hides(block, 'iconBtn')).toBe(false);
    expect(css).not.toMatch(/iconBtnOptional/);
    // Заглушки колокольчика больше нет.
    expect(css).not.toMatch(/iconBtnPlaceholder/);
  });

  test('шире 600px hamburger скрыт', () => {
    expect(css).toMatch(/\.menuBtn\s*\{[^}]*display:\s*none/);
  });
});

describe('resolveBreadcrumbs', () => {
  const crumbLabels = {
    '/psychologist': 'Главная',
    '/psychologist/students': 'Мои студенты',
    '/psychologist/tests': 'Тесты',
  };
  const dynamicCrumbs = [
    { prefix: '/psychologist/students/', label: 'Карточка студента', parent: '/psychologist/students' },
    { prefix: '/psychologist/other/', label: 'Без раздела' },
  ];
  const resolve = (pathname) =>
    resolveBreadcrumbs({ pathname, homePath: '/psychologist', crumbLabels, dynamicCrumbs });

  test('корень кабинета — одна текущая крошка «Главная»', () => {
    expect(resolve('/psychologist')).toEqual([{ label: 'Главная' }]);
    expect(resolve('/psychologist/')).toEqual([{ label: 'Главная' }]);
  });

  test('раздел из явной подписи', () => {
    expect(resolve('/psychologist/students')).toEqual([
      { label: 'Главная', to: '/psychologist' },
      { label: 'Мои студенты' },
    ]);
  });

  test('динамическая страница с parent — три уровня', () => {
    expect(resolve('/psychologist/students/42')).toEqual([
      { label: 'Главная', to: '/psychologist' },
      { label: 'Мои студенты', to: '/psychologist/students' },
      { label: 'Карточка студента' },
    ]);
  });

  test('динамическая страница без parent — два уровня', () => {
    expect(resolve('/psychologist/other/1')).toEqual([
      { label: 'Главная', to: '/psychologist' },
      { label: 'Без раздела' },
    ]);
  });

  test('вложенная страница без подписи — ближайший известный раздел, не сегмент URL', () => {
    expect(resolve('/psychologist/tests/catalog')).toEqual([
      { label: 'Главная', to: '/psychologist' },
      { label: 'Тесты', to: '/psychologist/tests' },
    ]);
  });

  test('неизвестный путь — только «Главная»', () => {
    expect(resolve('/psychologist/unknown')).toEqual([{ label: 'Главная', to: '/psychologist' }]);
  });
});
