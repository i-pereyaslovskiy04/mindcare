const DEFAULT_MARGIN = 8;
const DEFAULT_GAP = 4;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function computeActionsMenuPosition(anchorRect, menuSize, viewportSize, opts = {}) {
  const margin = opts.margin ?? DEFAULT_MARGIN;
  const gap = opts.gap ?? DEFAULT_GAP;
  const menuWidth = menuSize.width;
  const menuHeight = menuSize.height;
  const maxLeft = Math.max(margin, viewportSize.width - menuWidth - margin);
  const maxTop = Math.max(margin, viewportSize.height - menuHeight - margin);
  const spaceBelow = viewportSize.height - margin - anchorRect.bottom - gap;
  const spaceAbove = anchorRect.top - margin - gap;
  const placement = spaceBelow >= menuHeight || spaceBelow >= spaceAbove ? 'down' : 'up';
  const preferredTop = placement === 'down'
    ? anchorRect.bottom + gap
    : anchorRect.top - menuHeight - gap;
  const preferredLeft = anchorRect.right - menuWidth;

  return {
    top: clamp(preferredTop, margin, maxTop),
    left: clamp(preferredLeft, margin, maxLeft),
    placement,
  };
}
