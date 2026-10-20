import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

/**
 * Панель, привязанная к кнопке-триггеру: позиция (position: fixed) считается
 * от неё и пересчитывается на scroll/resize. Панель может рендериться в
 * портал, поэтому закрытие по клику снаружи проверяет и обёртку триггера
 * (wrapRef), и саму панель по id.
 *
 * Панель прижимается правым краем к правому краю триггера и не выходит за
 * экран: `gutter` — минимальный отступ от краёв окна.
 *
 * Используется ThemeToggle (панели «Оформление» и палитры) и колокольчиком
 * шапки (features/bell).
 */
export default function useAnchoredPanel(panelId, minPanelWidth, { gutter = 12 } = {}) {
  const [isOpen, setIsOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0, minWidth: 0 });

  const wrapRef = useRef(null);
  const triggerRef = useRef(null);

  const calcPos = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    // Панель может быть шире минимума (содержимое) — после монтирования
    // учитываем её реальную ширину, иначе она уезжает за правый край экрана.
    const rendered = document.getElementById(panelId)?.offsetWidth ?? 0;
    const width = Math.max(r.width, minPanelWidth);
    const outer = Math.max(width, rendered);
    const left = Math.max(gutter, Math.min(r.right - outer, window.innerWidth - outer - gutter));
    setPos({ top: r.bottom + 6, left, minWidth: width });
  }, [panelId, minPanelWidth, gutter]);

  const close = useCallback(() => setIsOpen(false), []);

  useLayoutEffect(() => {
    if (isOpen) calcPos();
  }, [isOpen, calcPos]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onOutside = (e) => {
      const panel = document.getElementById(panelId);
      if (!wrapRef.current?.contains(e.target) && !panel?.contains(e.target)) close();
    };
    const reposition = () => calcPos();
    document.addEventListener('mousedown', onOutside, true);
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);
    return () => {
      document.removeEventListener('mousedown', onOutside, true);
      window.removeEventListener('scroll', reposition, true);
      window.removeEventListener('resize', reposition);
    };
  }, [isOpen, panelId, close, calcPos]);

  return { isOpen, setIsOpen, close, calcPos, pos, wrapRef, triggerRef };
}
