import { computeActionsMenuPosition } from './actionsMenuPosition';

const menuSize = { width: 150, height: 80 };
const viewportSize = { width: 360, height: 640 };

test('positions the actions menu below the anchor when there is enough space', () => {
  expect(computeActionsMenuPosition(
    { top: 100, bottom: 126, left: 250, right: 276 },
    menuSize,
    viewportSize,
  )).toEqual({ top: 130, left: 126, placement: 'down' });
});

test('flips the actions menu above the anchor near the viewport bottom', () => {
  expect(computeActionsMenuPosition(
    { top: 590, bottom: 616, left: 250, right: 276 },
    menuSize,
    viewportSize,
  )).toEqual({ top: 506, left: 126, placement: 'up' });
});

test('clamps the actions menu horizontally inside the viewport', () => {
  expect(computeActionsMenuPosition(
    { top: 100, bottom: 126, left: 10, right: 36 },
    menuSize,
    viewportSize,
  )).toEqual({ top: 130, left: 8, placement: 'down' });
});

test('clamps the actions menu on a narrow mobile viewport', () => {
  expect(computeActionsMenuPosition(
    { top: 180, bottom: 206, left: 314, right: 340 },
    { width: 150, height: 80 },
    { width: 320, height: 360 },
  )).toEqual({ top: 210, left: 162, placement: 'down' });
});

test('clamps the actions menu vertically when both sides are tight', () => {
  expect(computeActionsMenuPosition(
    { top: 150, bottom: 176, left: 250, right: 276 },
    { width: 150, height: 180 },
    { width: 360, height: 190 },
  )).toEqual({ top: 8, left: 126, placement: 'up' });
});
