import { useEffect } from 'react';

/**
 * Прокрутка к разделу страницы и перенос фокуса на его заголовок (элемент с
 * data-section-heading и tabIndex=-1): экранный диктор озвучивает раздел, а
 * Tab продолжается с него. Без элемента — ничего не делает.
 */
export function scrollToSection(id) {
  const el = document.getElementById(id);
  if (!el) return false;
  if (typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  const heading = el.querySelector('[data-section-heading]');
  if (heading && typeof heading.focus === 'function') heading.focus({ preventScroll: true });
  return true;
}

/**
 * Переход по ссылке вида «/путь#раздел»: когда содержимое готово (ready),
 * страница прокручивается к разделу из location.hash. Повторно — только при
 * новом переходе (смена ready/hash).
 */
export default function useScrollToHash(ready) {
  const hash = typeof window !== 'undefined' ? window.location.hash : '';
  useEffect(() => {
    if (!ready || !hash || hash.length < 2) return;
    scrollToSection(decodeURIComponent(hash.slice(1)));
  }, [ready, hash]);
}
