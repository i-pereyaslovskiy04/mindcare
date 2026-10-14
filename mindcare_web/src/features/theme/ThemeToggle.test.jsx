import { render, screen, fireEvent, within } from '@testing-library/react';
import { ThemeProvider } from './ThemeContext';
import ThemeToggle from './ThemeToggle';

describe('ThemeToggle + ThemeProvider', () => {
  afterEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  test('без ThemeProvider рендерится null', () => {
    const { container } = render(<ThemeToggle />);
    expect(container).toBeEmptyDOMElement();
  });

  test('рендерит три режима, по умолчанию активна «Системная»', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    const group = screen.getByRole('group', { name: 'Режим темы оформления' });
    expect(within(group).getAllByRole('button')).toHaveLength(3);
    // jsdom без matchMedia → system резолвится в light
    expect(screen.getByRole('button', { name: /Системная тема/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(document.documentElement.getAttribute('data-theme')).toBe('dongu-light');
  });

  test('палитра по умолчанию — ДонГУ (чистый localStorage, без prefers-contrast)', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    // jsdom без matchMedia → нет prefers-contrast и prefers-color-scheme:
    // дефолтная палитра dongu, режим system резолвится в light.
    expect(document.documentElement.getAttribute('data-theme')).toBe('dongu-light');
    expect(
      screen.getByRole('button', { name: 'Цветовая тема: ДонГУ' })
    ).toBeInTheDocument();
  });

  test('клик «Тёмная тема» ставит data-theme=dongu-dark и сохраняет выбор', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('dongu-dark');
    expect(localStorage.getItem('app-theme-mode')).toBe('dark');
    expect(screen.getByRole('button', { name: 'Тёмная тема' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
  });

  test('сохранённый режим восстанавливается при монтировании', () => {
    localStorage.setItem('app-theme-mode', 'dark');
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    expect(document.documentElement.getAttribute('data-theme')).toBe('dongu-dark');
  });

  test('невалидное значение в localStorage игнорируется (fallback system)', () => {
    localStorage.setItem('app-theme-mode', 'neon');
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    expect(document.documentElement.getAttribute('data-theme')).toBe('dongu-light');
    expect(screen.getByRole('button', { name: /Системная тема/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
  });

  test('палитры скрыты в выпадающем меню, пока оно не открыто', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    const trigger = screen.getByRole('button', { name: 'Цветовая тема: ДонГУ' });
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(trigger);
    const listbox = screen.getByRole('listbox', { name: 'Цветовая тема' });
    // Контрастная палитра в обычном списке не предлагается — она относится к
    // версии для слабовидящих.
    expect(within(listbox).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'ДонГУ', 'Кофе', 'Природа', 'Классика',
    ]);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
  });

  test('выбор палитры «Природная» ставит nature-*, закрывает меню и сохраняется', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Цветовая тема: ДонГУ' }));
    fireEvent.mouseDown(
      screen.getByRole('option', { name: 'Палитра «Природное спокойствие»' })
    );

    expect(document.documentElement.getAttribute('data-theme')).toBe('nature-light');
    expect(localStorage.getItem('app-theme-palette')).toBe('nature');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Цветовая тема: Природа' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('nature-dark');
  });

  test('палитра «Классика» выбирается с клавиатуры (стрелки + Enter)', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    const trigger = screen.getByRole('button', { name: 'Цветовая тема: ДонГУ' });
    fireEvent.keyDown(trigger, { key: 'ArrowDown' }); // открывает меню на «ДонГУ»
    fireEvent.keyDown(trigger, { key: 'ArrowDown' }); // Кофе
    fireEvent.keyDown(trigger, { key: 'ArrowDown' }); // Природа
    fireEvent.keyDown(trigger, { key: 'ArrowDown' }); // Классика
    fireEvent.keyDown(trigger, { key: 'Enter' });

    expect(document.documentElement.getAttribute('data-theme')).toBe('classic-light');
    expect(localStorage.getItem('app-theme-palette')).toBe('classic');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  test('Escape закрывает меню без смены палитры', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    const trigger = screen.getByRole('button', { name: 'Цветовая тема: ДонГУ' });
    fireEvent.click(trigger);
    fireEvent.keyDown(trigger, { key: 'Escape' });

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dongu-light');
  });

  test('уже активная контрастная тема видна в меню, режим по-прежнему работает', () => {
    // hc остаётся палитрой ThemeContext (prefers-contrast / прежний выбор):
    // если она активна, пункт показывается — текущий выбор не пропадает.
    localStorage.setItem('app-theme-palette', 'hc');
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    expect(document.documentElement.getAttribute('data-theme')).toBe('hc-light');

    fireEvent.click(screen.getByRole('button', { name: 'Цветовая тема: Контраст' }));
    expect(
      screen.getByRole('option', { name: 'Высококонтрастная тема (для слабовидящих)' })
    ).toHaveAttribute('aria-selected', 'true');

    fireEvent.mouseDown(screen.getByRole('option', { name: 'Кофейная палитра' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('coffee-light');

    // После смены палитры контрастный пункт из обычного списка уходит.
    fireEvent.click(screen.getByRole('button', { name: 'Цветовая тема: Кофе' }));
    expect(
      screen.queryByRole('option', { name: 'Высококонтрастная тема (для слабовидящих)' })
    ).not.toBeInTheDocument();
  });

  test('сохранённая hc: режим «Тёмная» даёт hc-dark', () => {
    localStorage.setItem('app-theme-palette', 'hc');
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('hc-dark');
  });

  test('withPalette=false скрывает выбор палитры', () => {
    render(
      <ThemeProvider>
        <ThemeToggle withPalette={false} />
      </ThemeProvider>
    );
    expect(
      screen.queryByRole('button', { name: /Цветовая тема/ })
    ).not.toBeInTheDocument();
  });

  test('compact: в шапке одна иконка-кнопка, режим и палитра скрыты до открытия', () => {
    render(
      <ThemeProvider>
        <ThemeToggle compact />
      </ThemeProvider>
    );

    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(screen.queryByRole('group', { name: 'Режим темы оформления' })).not.toBeInTheDocument();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    const trigger = screen.getByRole('button', { name: 'Оформление: ДонГУ' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(trigger);

    const panel = screen.getByRole('dialog', { name: 'Оформление' });
    expect(
      within(panel).getAllByRole('button', { name: /тема/i }).length
    ).toBeGreaterThanOrEqual(3);
    // Палитры — кнопки с aria-pressed (выбор с клавиатуры), без контрастной.
    const palettes = within(panel).getByRole('group', { name: 'Цветовая тема' });
    expect(within(palettes).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'ДонГУ', 'Кофе', 'Природа', 'Классика',
    ]);
    expect(within(palettes).getByRole('button', { name: /ДонГУ/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
  });

  test('compact: режим и палитра выбираются из панели, панель остаётся открытой', () => {
    render(
      <ThemeProvider>
        <ThemeToggle compact />
      </ThemeProvider>
    );

    fireEvent.click(screen.getByRole('button', { name: 'Оформление: ДонГУ' }));
    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('dongu-dark');

    fireEvent.click(
      screen.getByRole('button', { name: 'Палитра «Природное спокойствие»' })
    );
    expect(document.documentElement.getAttribute('data-theme')).toBe('nature-dark');
    expect(
      screen.getByRole('button', { name: 'Палитра «Природное спокойствие»' })
    ).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('dialog', { name: 'Оформление' })).toBeInTheDocument();
  });

  test('compact: при открытии фокус в панели, Tab ходит по кругу внутри неё', () => {
    render(
      <ThemeProvider>
        <ThemeToggle compact />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Оформление: ДонГУ' }));

    const panel = screen.getByRole('dialog', { name: 'Оформление' });
    // Фокус — на выбранном режиме (jsdom: «Системная»).
    expect(screen.getByRole('button', { name: /Системная тема/ })).toHaveFocus();

    const buttons = within(panel).getAllByRole('button');
    const first = buttons[0];
    const last = buttons[buttons.length - 1];

    last.focus();
    fireEvent.keyDown(last, { key: 'Tab' });
    expect(first).toHaveFocus();

    fireEvent.keyDown(first, { key: 'Tab', shiftKey: true });
    expect(last).toHaveFocus();
  });

  test('compact: Escape возвращает фокус на кнопку «Оформление»', () => {
    render(
      <ThemeProvider>
        <ThemeToggle compact />
      </ThemeProvider>
    );
    const trigger = screen.getByRole('button', { name: 'Оформление: ДонГУ' });
    fireEvent.click(trigger);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(trigger).toHaveFocus();
  });

  test('compact: клик вне панели закрывает её', () => {
    render(
      <ThemeProvider>
        <ThemeToggle compact />
        <p>снаружи</p>
      </ThemeProvider>
    );
    const trigger = screen.getByRole('button', { name: 'Оформление: ДонГУ' });
    fireEvent.click(trigger);
    fireEvent.mouseDown(screen.getByText('снаружи'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  test('compact: label задаёт имя триггера, extraSection — отдельная секция панели', () => {
    const renderSection = jest.fn(({ close }) => (
      <button type="button" onClick={close}>Действие секции</button>
    ));
    render(
      <ThemeProvider>
        <ThemeToggle
          compact
          label="Оформление и версия для слабовидящих"
          extraSection={{ title: 'Версия для слабовидящих', render: renderSection }}
        />
      </ThemeProvider>
    );

    const trigger = screen.getByRole('button', { name: 'Оформление и версия для слабовидящих' });
    expect(trigger).toHaveAttribute('aria-haspopup', 'dialog');
    expect(trigger).not.toHaveAttribute('aria-controls');
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-controls', screen.getByRole('dialog').id);

    expect(screen.getByRole('group', { name: 'Оформление' })).toBeInTheDocument();
    const extra = screen.getByRole('group', { name: 'Версия для слабовидящих' });
    expect(within(extra).getByRole('button', { name: 'Действие секции' })).toBeInTheDocument();
    expect(screen.getByRole('separator')).toBeInTheDocument();

    // close из секции закрывает панель и возвращает фокус на триггер.
    fireEvent.click(screen.getByRole('button', { name: 'Действие секции' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  test('compact: Escape закрывает панель', () => {
    render(
      <ThemeProvider>
        <ThemeToggle compact />
      </ThemeProvider>
    );

    fireEvent.click(screen.getByRole('button', { name: 'Оформление: ДонГУ' }));
    expect(screen.getByRole('dialog', { name: 'Оформление' })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dongu-light');
  });

  test('переключение обратно на «Светлая» работает', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }));
    fireEvent.click(screen.getByRole('button', { name: 'Светлая тема' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('dongu-light');
    expect(localStorage.getItem('app-theme-mode')).toBe('light');
  });
});
