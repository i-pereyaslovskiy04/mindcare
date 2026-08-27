import { render, screen, act, fireEvent } from '@testing-library/react';
import Hero from './Hero';

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

describe('Hero', () => {
  const originalMatchMedia = window.matchMedia;

  beforeEach(() => {
    jest.useFakeTimers();
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
});
