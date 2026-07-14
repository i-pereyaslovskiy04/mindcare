/**
 * Режим для слабовидящих (ГОСТ Р 52872-2019): контекст, кнопка, панель.
 */

import { render, screen, fireEvent, within } from '@testing-library/react';
import { A11yProvider } from './A11yContext';
import A11yToggle from './A11yToggle';
import A11yPanel from './A11yPanel';

function renderA11y() {
  return render(
    <A11yProvider>
      <A11yToggle />
      <A11yPanel />
    </A11yProvider>
  );
}

const root = () => document.documentElement;

describe('A11y (ГОСТ) режим', () => {
  afterEach(() => {
    localStorage.clear();
    ['data-a11y', 'data-a11y-scheme', 'data-a11y-spacing', 'data-a11y-leading',
      'data-a11y-font', 'data-a11y-images'].forEach((a) => root().removeAttribute(a));
    root().style.removeProperty('--a11y-font-scale');
  });

  test('вне провайдера кнопка и панель рендерятся как null', () => {
    const { container } = render(<><A11yToggle /><A11yPanel /></>);
    expect(container).toBeEmptyDOMElement();
  });

  test('по умолчанию режим выключен: панели нет, атрибутов нет', () => {
    renderA11y();
    expect(root().hasAttribute('data-a11y')).toBe(false);
    expect(
      screen.queryByRole('region', { name: 'Настройки версии для слабовидящих' })
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Версия для слабовидящих' })
    ).toHaveAttribute('aria-pressed', 'false');
  });

  test('включение режима ставит data-a11y и показывает панель', () => {
    renderA11y();
    fireEvent.click(screen.getByRole('button', { name: 'Версия для слабовидящих' }));

    expect(root().getAttribute('data-a11y')).toBe('on');
    expect(root().getAttribute('data-a11y-scheme')).toBe('bw');
    expect(root().style.getPropertyValue('--a11y-font-scale')).toBe('1');
    expect(
      screen.getByRole('region', { name: 'Настройки версии для слабовидящих' })
    ).toBeInTheDocument();
    // Кнопка превращается в «Обычная версия».
    expect(
      screen.getByRole('button', { name: 'Обычная версия сайта' })
    ).toHaveAttribute('aria-pressed', 'true');
  });

  test('размер шрифта 200% (A++) применяется', () => {
    renderA11y();
    fireEvent.click(screen.getByRole('button', { name: 'Версия для слабовидящих' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Очень крупный размер шрифта (200%)' })
    );
    expect(root().style.getPropertyValue('--a11y-font-scale')).toBe('2');
  });

  test('переключение цветовой схемы (Б/Ч, синяя, бежевая)', () => {
    renderA11y();
    fireEvent.click(screen.getByRole('button', { name: 'Версия для слабовидящих' }));

    fireEvent.click(screen.getByRole('button', { name: 'Белым по чёрному' }));
    expect(root().getAttribute('data-a11y-scheme')).toBe('wb');

    fireEvent.click(screen.getByRole('button', { name: 'Тёмно-синим по голубому' }));
    expect(root().getAttribute('data-a11y-scheme')).toBe('blue');

    fireEvent.click(screen.getByRole('button', { name: 'Коричневым по бежевому' }));
    expect(root().getAttribute('data-a11y-scheme')).toBe('beige');
  });

  test('интервалы, шрифт и изображения применяются', () => {
    renderA11y();
    fireEvent.click(screen.getByRole('button', { name: 'Версия для слабовидящих' }));

    fireEvent.click(screen.getByRole('button', { name: 'Большой межбуквенный интервал' }));
    fireEvent.click(screen.getByRole('button', { name: 'Межстрочный интервал 2' }));
    fireEvent.click(screen.getByRole('button', { name: 'Шрифт с засечками' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Изображения в оттенках серого' })
    );

    expect(root().getAttribute('data-a11y-spacing')).toBe('large');
    expect(root().getAttribute('data-a11y-leading')).toBe('2');
    expect(root().getAttribute('data-a11y-font')).toBe('serif');
    expect(root().getAttribute('data-a11y-images')).toBe('gray');
  });

  test('«Скрыть изображения» снимает src (остаётся alt) и возвращает обратно', () => {
    const img = document.createElement('img');
    img.setAttribute('src', '/media/photo.jpg');
    img.setAttribute('alt', 'Фото психолога');
    document.body.appendChild(img);

    renderA11y();
    fireEvent.click(screen.getByRole('button', { name: 'Версия для слабовидящих' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Скрыть изображения (останется описание)' })
    );

    expect(img.hasAttribute('src')).toBe(false);
    expect(img.getAttribute('alt')).toBe('Фото психолога'); // смысл сохранён

    fireEvent.click(screen.getByRole('button', { name: 'Показывать изображения' }));
    expect(img.getAttribute('src')).toBe('/media/photo.jpg');

    document.body.removeChild(img);
  });

  test('настройки сохраняются и восстанавливаются при следующем визите', () => {
    const { unmount } = renderA11y();
    fireEvent.click(screen.getByRole('button', { name: 'Версия для слабовидящих' }));
    fireEvent.click(screen.getByRole('button', { name: 'Белым по чёрному' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Крупный размер шрифта (150%)' })
    );
    unmount();

    renderA11y();
    expect(root().getAttribute('data-a11y')).toBe('on');
    expect(root().getAttribute('data-a11y-scheme')).toBe('wb');
    expect(root().style.getPropertyValue('--a11y-font-scale')).toBe('1.5');
  });

  test('«Сбросить настройки» возвращает значения по умолчанию, режим остаётся', () => {
    renderA11y();
    fireEvent.click(screen.getByRole('button', { name: 'Версия для слабовидящих' }));
    fireEvent.click(screen.getByRole('button', { name: 'Белым по чёрному' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Очень крупный размер шрифта (200%)' })
    );

    fireEvent.click(screen.getByRole('button', { name: 'Сбросить настройки' }));

    expect(root().getAttribute('data-a11y')).toBe('on');
    expect(root().getAttribute('data-a11y-scheme')).toBe('bw');
    expect(root().style.getPropertyValue('--a11y-font-scale')).toBe('1');
  });

  test('выход из режима убирает атрибуты и панель', () => {
    renderA11y();
    fireEvent.click(screen.getByRole('button', { name: 'Версия для слабовидящих' }));
    fireEvent.click(screen.getByRole('button', { name: 'Обычная версия сайта' }));

    expect(root().hasAttribute('data-a11y')).toBe(false);
    expect(root().style.getPropertyValue('--a11y-font-scale')).toBe('');
    expect(
      screen.queryByRole('region', { name: 'Настройки версии для слабовидящих' })
    ).not.toBeInTheDocument();
  });

  test('битые настройки в localStorage игнорируются (fallback к дефолтам)', () => {
    localStorage.setItem(
      'app-a11y-settings',
      JSON.stringify({ enabled: true, scheme: 'neon', fontScale: 42 })
    );
    renderA11y();
    expect(root().getAttribute('data-a11y-scheme')).toBe('bw');
    expect(root().style.getPropertyValue('--a11y-font-scale')).toBe('1');
  });

  test('compact: кнопка без подписи, доступное имя и состояние сохраняются', () => {
    render(
      <A11yProvider>
        <A11yToggle compact />
      </A11yProvider>
    );

    const btn = screen.getByRole('button', { name: 'Версия для слабовидящих' });
    expect(btn).toHaveTextContent('');
    expect(btn).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(btn);
    expect(root().getAttribute('data-a11y')).toBe('on');
    expect(
      screen.getByRole('button', { name: 'Обычная версия сайта' })
    ).toHaveAttribute('aria-pressed', 'true');
  });

  test('все контролы панели — button с aria-pressed (клавиатурная доступность)', () => {
    renderA11y();
    fireEvent.click(screen.getByRole('button', { name: 'Версия для слабовидящих' }));
    const panel = screen.getByRole('region', { name: 'Настройки версии для слабовидящих' });
    const buttons = within(panel).getAllByRole('button');
    // Кроме «Сбросить настройки», все контролы — выбор из набора.
    const choices = buttons.filter((b) => b.textContent !== 'Сбросить настройки');
    expect(choices.length).toBeGreaterThan(0);
    choices.forEach((b) => {
      expect(b).toHaveAttribute('type', 'button');
      expect(b).toHaveAttribute('aria-pressed');
    });
  });
});
