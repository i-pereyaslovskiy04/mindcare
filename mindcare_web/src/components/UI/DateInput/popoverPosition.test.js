import { computePopoverPosition } from './popoverPosition';

const SIZE = { width: 280, height: 300 };
const VIEWPORT = { width: 1024, height: 768 };

// gap=4, margin=12 по умолчанию
describe('computePopoverPosition', () => {
  test('достаточно места снизу → direction down, top под полем', () => {
    const anchor = { top: 100, bottom: 140, left: 200 };
    const pos = computePopoverPosition(anchor, SIZE, VIEWPORT);
    expect(pos.direction).toBe('down');
    expect(pos.top).toBe(144); // bottom + gap
    expect(pos.left).toBe(200);
  });

  test('снизу не хватает, сверху хватает → direction up над полем', () => {
    // bottom близко к нижней границе → снизу мало места; сверху много
    const anchor = { top: 600, bottom: 640, left: 200 };
    const pos = computePopoverPosition(anchor, SIZE, VIEWPORT);
    expect(pos.direction).toBe('up');
    expect(pos.top).toBe(600 - 300 - 4); // top - ph - gap = 296
  });

  test('переполнение справа → left зажат к правому краю', () => {
    const anchor = { top: 100, bottom: 140, left: 1000 };
    const pos = computePopoverPosition(anchor, SIZE, VIEWPORT);
    // vw - pw - margin = 1024 - 280 - 12 = 732
    expect(pos.left).toBe(732);
  });

  test('переполнение слева → left зажат к margin', () => {
    const anchor = { top: 100, bottom: 140, left: -50 };
    const pos = computePopoverPosition(anchor, SIZE, VIEWPORT);
    expect(pos.left).toBe(12);
  });

  test('тесно с обеих сторон → top зажат внутри viewport', () => {
    // маленький экран, высокий popover — никуда целиком не влезает
    const tightViewport = { width: 1024, height: 320 };
    const anchor = { top: 150, bottom: 190, left: 200 };
    const pos = computePopoverPosition(anchor, SIZE, tightViewport);
    expect(pos.top).toBeGreaterThanOrEqual(12);
    // не уходит за нижнюю границу
    expect(pos.top + SIZE.height).toBeLessThanOrEqual(tightViewport.height);
  });
});
