import { render, screen, act, fireEvent } from '@testing-library/react';
import Hero from './Hero';
import { useHeroSlides } from './useHeroSlides';

jest.mock('./useHeroSlides');

/** Мок matchMedia под конкретный ответ на prefers-reduced-motion. */
function mockReducedMotion(matches) {
  window.matchMedia = jest.fn().mockImplementation((query) => ({
    matches,
    media: query,
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
  }));
}

/** Контейнер баннера — по ARIA-роли региона, без обращения к DOM напрямую. */
function heroRegion() {
  return screen.getByRole('region', { name: 'Баннер главной страницы' });
}

/** Активный слайд — тот, у точки которого выставлен aria-current. */
function activeDotIndex() {
  const dots = screen.getAllByRole('button', { name: /^Слайд \d+$/ });
  return dots.findIndex((d) => d.getAttribute('aria-current') === 'true');
}

const FIXTURE_SLIDES = [
  { label: 'A', title: 'Заголовок 1', highlight: 'Акцент 1', sub: 'Подзаголовок 1', image_url: null },
  { label: 'B', title: 'Заголовок 2', highlight: 'Акцент 2', sub: 'Подзаголовок 2', image_url: null },
  { label: 'C', title: 'Заголовок 3', highlight: 'Акцент 3', sub: 'Подзаголовок 3', image_url: null },
];

describe('Hero', () => {
  const originalMatchMedia = window.matchMedia;

  beforeEach(() => {
    jest.useFakeTimers();
    useHeroSlides.mockReturnValue({ slides: FIXTURE_SLIDES, loading: false });
  });

  afterEach(() => {
    // Именно clear, а не runOnlyPendingTimers: RTL-cleanup идёт позже этого
    // хука, и догнанный таймер сработал бы на ещё смонтированном компоненте.
    jest.clearAllTimers();
    jest.useRealTimers();
    window.matchMedia = originalMatchMedia;
  });

  test('точки пагинации — настоящие кнопки, активная помечена aria-current', () => {
    render(<Hero />);

    const dots = screen.getAllByRole('button', { name: /^Слайд \d+$/ });
    expect(dots.length).toBeGreaterThan(1);
    dots.forEach((dot) => expect(dot).toHaveAttribute('type', 'button'));

    expect(activeDotIndex()).toBe(0);
  });

  test('клик по точке переключает слайд', () => {
    render(<Hero />);

    fireEvent.click(screen.getByRole('button', { name: 'Слайд 3' }));
    expect(activeDotIndex()).toBe(2);
  });

  test('автопрокрутка переключает слайд через 5 секунд', () => {
    render(<Hero />);

    expect(activeDotIndex()).toBe(0);
    act(() => { jest.advanceTimersByTime(5000); });
    expect(activeDotIndex()).toBe(1);
  });

  test('наведение курсора останавливает автопрокрутку', () => {
    render(<Hero />);
    const hero = heroRegion();

    fireEvent.mouseEnter(hero);
    act(() => { jest.advanceTimersByTime(15000); });
    expect(activeDotIndex()).toBe(0);

    fireEvent.mouseLeave(hero);
    act(() => { jest.advanceTimersByTime(5000); });
    expect(activeDotIndex()).toBe(1);
  });

  test('клик по стрелке при наведённом курсоре не возобновляет автопрокрутку', () => {
    render(<Hero />);
    const hero = heroRegion();

    fireEvent.mouseEnter(hero);
    fireEvent.click(screen.getByRole('button', { name: 'Следующий слайд' }));
    expect(activeDotIndex()).toBe(1);

    // Курсор всё ещё над баннером — таймер заводиться не должен.
    act(() => { jest.advanceTimersByTime(15000); });
    expect(activeDotIndex()).toBe(1);
  });

  test('фокус на точке ставит автопрокрутку на паузу, увод фокуса — снимает', () => {
    render(<Hero />);
    const dot = screen.getByRole('button', { name: 'Слайд 2' });

    fireEvent.focus(dot);
    act(() => { jest.advanceTimersByTime(15000); });
    expect(activeDotIndex()).toBe(0);

    fireEvent.blur(dot);
    act(() => { jest.advanceTimersByTime(5000); });
    expect(activeDotIndex()).toBe(1);
  });

  test('увод фокуса не снимает паузу, пока курсор над баннером', () => {
    render(<Hero />);
    const hero = heroRegion();
    const dot = screen.getByRole('button', { name: 'Слайд 2' });

    fireEvent.mouseEnter(hero);
    fireEvent.focus(dot);
    fireEvent.blur(dot);

    act(() => { jest.advanceTimersByTime(15000); });
    expect(activeDotIndex()).toBe(0);
  });

  test('prefers-reduced-motion: reduce — автопрокрутка не запускается', () => {
    mockReducedMotion(true);
    render(<Hero />);

    act(() => { jest.advanceTimersByTime(15000); });
    expect(activeDotIndex()).toBe(0);

    // Ручное переключение остаётся доступным.
    fireEvent.click(screen.getByRole('button', { name: 'Следующий слайд' }));
    expect(activeDotIndex()).toBe(1);
  });

  test('slides ещё загружаются — рендерится дефолтный fallback из трёх слайдов', () => {
    useHeroSlides.mockReturnValue({ slides: [], loading: true });
    render(<Hero />);

    const dots = screen.getAllByRole('button', { name: /^Слайд \d+$/ });
    expect(dots).toHaveLength(3);
  });

  test('нет активных слайдов в БД — рендерится дефолтный fallback', () => {
    useHeroSlides.mockReturnValue({ slides: [], loading: false });
    render(<Hero />);

    const dots = screen.getAllByRole('button', { name: /^Слайд \d+$/ });
    expect(dots).toHaveLength(3);
  });

  test('слайд с картинкой — фоновый слой рендерится синхронно с activeIndex', () => {
    useHeroSlides.mockReturnValue({
      slides: [
        { title: 'С картинкой', image_url: 'https://example.test/slide-1.webp' },
        { title: 'Без картинки', image_url: null },
      ],
      loading: false,
    });
    render(<Hero />);

    const bg = screen.getByTestId('hero-slide-bg-0');
    expect(bg).toHaveClass('slideActive');
    expect(screen.queryByTestId('hero-slide-bg-1')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Слайд 2' }));
    expect(bg).not.toHaveClass('slideActive');
  });

  test('слайд без label/highlight/sub — пустые элементы не рендерятся', () => {
    useHeroSlides.mockReturnValue({
      slides: [{ title: 'Только заголовок', label: null, highlight: null, sub: null }],
      loading: false,
    });
    render(<Hero />);

    expect(screen.getByRole('heading', { name: 'Только заголовок' })).toBeInTheDocument();
    expect(screen.queryByText('null')).not.toBeInTheDocument();
  });

  test('слайд без link_url — CTA-кнопка не рендерится', () => {
    useHeroSlides.mockReturnValue({
      slides: [{ title: 'Без ссылки', link_url: null }],
      loading: false,
    });
    render(<Hero />);

    expect(screen.queryByRole('link', { name: 'Подробнее' })).not.toBeInTheDocument();
  });

  test('слайд с link_url — CTA-кнопка ведёт по ссылке, у неактивного слайда tabIndex=-1', () => {
    useHeroSlides.mockReturnValue({
      slides: [
        { title: 'Со ссылкой', link_url: '/services' },
        { title: 'Второй слайд', link_url: null },
      ],
      loading: false,
    });
    render(<Hero />);

    const cta = screen.getByRole('link', { name: 'Подробнее' });
    expect(cta).toHaveAttribute('href', '/services');
    expect(cta).not.toHaveAttribute('tabindex');

    fireEvent.click(screen.getByRole('button', { name: 'Слайд 2' }));
    // Слайд со ссылкой стал неактивным — CTA не должна попадать в Tab-обход.
    expect(cta).toHaveAttribute('tabindex', '-1');
  });

  test('слайд с картинкой получает класс hasImage (подложка под текст)', () => {
    useHeroSlides.mockReturnValue({
      slides: [
        { title: 'С картинкой', image_url: 'https://example.test/slide-1.webp' },
        { title: 'Без картинки', image_url: null },
      ],
      loading: false,
    });
    render(<Hero />);

    expect(screen.getByTestId('hero-slide-0')).toHaveClass('hasImage');
    expect(screen.getByTestId('hero-slide-1')).not.toHaveClass('hasImage');
  });

  test('placement передаётся в useHeroSlides и влияет на fallback/aria-label', () => {
    useHeroSlides.mockImplementation(() => ({ slides: [], loading: true }));
    render(<Hero placement="services" />);

    expect(useHeroSlides).toHaveBeenCalledWith('services');
    expect(
      screen.getByRole('region', { name: 'Баннер страницы услуг' })
    ).toBeInTheDocument();
    // Fallback для 'services' — один слайд (не 3, как у 'home'), поэтому
    // точки-индикаторы не рендерятся (см. отдельный тест ниже).
    expect(screen.queryAllByRole('button', { name: /^Слайд \d+$/ })).toHaveLength(0);
  });

  test('один слайд — стрелки и точки-индикаторы не рендерятся', () => {
    useHeroSlides.mockReturnValue({
      slides: [{ title: 'Единственный слайд' }],
      loading: false,
    });
    render(<Hero />);

    expect(screen.queryByRole('button', { name: 'Следующий слайд' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Предыдущий слайд' })).not.toBeInTheDocument();
    expect(screen.queryAllByRole('button', { name: /^Слайд \d+$/ })).toHaveLength(0);
  });

  test.each([
    ['about',     'Баннер страницы «О центре»',      'Ресурсный центр'],
    ['materials', 'Баннер страницы материалов',      'Материалы'],
  ])('placement=%s — свой fallback и aria-label', (placement, ariaLabel, title) => {
    useHeroSlides.mockImplementation(() => ({ slides: [], loading: true }));
    render(<Hero placement={placement} />);

    expect(useHeroSlides).toHaveBeenCalledWith(placement);
    expect(screen.getByRole('region', { name: ariaLabel })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: new RegExp(title) })).toBeInTheDocument();
    // Один слайд — управление не рендерится.
    expect(screen.queryAllByRole('button', { name: /^Слайд \d+$/ })).toHaveLength(0);
  });

  test('без placement — прежнее поведение по умолчанию (home)', () => {
    useHeroSlides.mockImplementation(() => ({ slides: [], loading: true }));
    render(<Hero />);

    expect(useHeroSlides).toHaveBeenCalledWith('home');
  });
});
