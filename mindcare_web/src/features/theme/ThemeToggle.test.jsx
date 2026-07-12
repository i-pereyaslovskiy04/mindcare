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
    expect(document.documentElement.getAttribute('data-theme')).toBe('coffee-light');
  });

  test('клик «Тёмная тема» ставит data-theme=coffee-dark и сохраняет выбор', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('coffee-dark');
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
    expect(document.documentElement.getAttribute('data-theme')).toBe('coffee-dark');
  });

  test('невалидное значение в localStorage игнорируется (fallback system)', () => {
    localStorage.setItem('app-theme-mode', 'neon');
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    expect(document.documentElement.getAttribute('data-theme')).toBe('coffee-light');
    expect(screen.getByRole('button', { name: /Системная тема/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
  });

  test('выбор палитры «Природная» ставит nature-* и сохраняется', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Палитра «Природное спокойствие»' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('nature-light');
    expect(localStorage.getItem('app-theme-palette')).toBe('nature');
    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('nature-dark');
  });

  test('withPalette=false скрывает выбор палитры', () => {
    render(
      <ThemeProvider>
        <ThemeToggle withPalette={false} />
      </ThemeProvider>
    );
    expect(
      screen.queryByRole('group', { name: 'Цветовая палитра' })
    ).not.toBeInTheDocument();
  });

  test('переключение обратно на «Светлая» работает', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }));
    fireEvent.click(screen.getByRole('button', { name: 'Светлая тема' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('coffee-light');
    expect(localStorage.getItem('app-theme-mode')).toBe('light');
  });
});
