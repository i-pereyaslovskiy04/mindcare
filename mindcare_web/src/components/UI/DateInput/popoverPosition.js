/**
 * Pure-функция позиционирования popover относительно anchor-поля.
 *
 * Открывает вниз под полем, если снизу хватает места; иначе вверх, если сверху
 * хватает; иначе — в сторону с бо́льшим запасом, с зажатием в пределах viewport.
 * Горизонтально выравнивает по левому краю anchor и зажимает в [margin, …].
 *
 * Все размеры — в px (как из getBoundingClientRect / window.innerWidth/Height).
 *
 * @returns {{ top: number, left: number, direction: 'up'|'down' }}
 */
export function computePopoverPosition(anchorRect, popoverSize, viewportSize, opts = {}) {
  const gap = opts.gap ?? 4;
  const margin = opts.margin ?? 12;
  const { width: pw, height: ph } = popoverSize;
  const { width: vw, height: vh } = viewportSize;

  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), Math.max(lo, hi));

  const left = clamp(anchorRect.left, margin, vw - pw - margin);

  const spaceBelow = vh - anchorRect.bottom;
  const spaceAbove = anchorRect.top;
  const fits = (space) => space >= ph + gap;

  if (fits(spaceBelow)) {
    return { top: anchorRect.bottom + gap, left, direction: 'down' };
  }
  if (fits(spaceAbove)) {
    return { top: anchorRect.top - ph - gap, left, direction: 'up' };
  }

  // Ни вниз, ни вверх целиком не помещается — открываем в сторону с бо́льшим
  // запасом и зажимаем top в пределах viewport (с учётом margin).
  const direction = spaceBelow >= spaceAbove ? 'down' : 'up';
  const rawTop = direction === 'down'
    ? anchorRect.bottom + gap
    : anchorRect.top - ph - gap;
  const top = clamp(rawTop, margin, vh - ph - margin);

  return { top, left, direction };
}
