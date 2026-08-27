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
    expect(within(listbox).getAllByRole('option')).toHaveLength(5);
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

  test('контрастная тема: hc-light, режим по-прежнему работает', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Цветовая тема: ДонГУ' }));
    fireEvent.mouseDown(
      screen.getByRole('option', { name: 'Высококонтрастная тема (для слабовидящих)' })
    );
    expect(document.documentElement.getAttribute('data-theme')).toBe('hc-light');
    expect(localStorage.getItem('app-theme-palette')).toBe('hc');

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
    expect(within(panel).getAllByRole('option')).toHaveLength(5);
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

    fireEvent.mouseDown(
      screen.getByRole('option', { name: 'Палитра «Природное спокойствие»' })
    );
    expect(document.documentElement.getAttribute('data-theme')).toBe('nature-dark');
    expect(screen.getByRole('dialog', { name: 'Оформление' })).toBeInTheDocument();
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
