import { correctedPage, lastPageOf } from './pagination';

test('lastPageOf: минимум 1, total=0 → 1', () => {
  expect(lastPageOf(0, 20)).toBe(1);
  expect(lastPageOf(20, 20)).toBe(1);
  expect(lastPageOf(21, 20)).toBe(2);
  expect(lastPageOf(undefined, 20)).toBe(1);
});

test('непустая страница и страница 1 не меняются', () => {
  expect(correctedPage(3, 20, 5, 45)).toBe(3);
  expect(correctedPage(1, 20, 0, 0)).toBe(1);
});

test('опустевшая последняя страница → последняя существующая', () => {
  // Было 41 запись (3 страницы), последнюю отключили: total=40 → страница 2.
  expect(correctedPage(3, 20, 0, 40)).toBe(2);
  // Сразу несколько страниц исчезли.
  expect(correctedPage(5, 20, 0, 21)).toBe(2);
});

test('исчезновение всех записей на странице > 1 → страница 1', () => {
  expect(correctedPage(4, 20, 0, 0)).toBe(1);
});

test('рассогласование count и страницы: шаг назад, без зацикливания', () => {
  // total ещё 60 (3 страницы), но страница 3 пуста → 2, а не снова 3.
  expect(correctedPage(3, 20, 0, 60)).toBe(2);
});
