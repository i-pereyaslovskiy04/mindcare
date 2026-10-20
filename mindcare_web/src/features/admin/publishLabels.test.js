import { publishCheckboxLabel, submitButtonLabel } from './publishLabels';

describe('publishCheckboxLabel', () => {
  test('всегда "Опубликовать" (независимо от состояния)', () => {
    expect(publishCheckboxLabel(true)).toBe('Опубликовать');
    expect(publishCheckboxLabel(false)).toBe('Опубликовать');
    expect(publishCheckboxLabel()).toBe('Опубликовать');
  });
});

describe('submitButtonLabel', () => {
  test('submitting перекрывает всё', () => {
    expect(submitButtonLabel({ isEdit: false, isPublished: true, submitting: true }))
      .toBe('Сохранение…');
  });

  test('create + published → "Создать и опубликовать"', () => {
    expect(submitButtonLabel({ isEdit: false, isPublished: true, submitting: false }))
      .toBe('Создать и опубликовать');
  });

  test('create + draft → "Сохранить черновик"', () => {
    expect(submitButtonLabel({ isEdit: false, isPublished: false, submitting: false }))
      .toBe('Сохранить черновик');
  });

  test('edit + published → "Сохранить и опубликовать"', () => {
    expect(submitButtonLabel({ isEdit: true, isPublished: true, submitting: false }))
      .toBe('Сохранить и опубликовать');
  });

  test('edit + draft → "Сохранить как черновик"', () => {
    expect(submitButtonLabel({ isEdit: true, isPublished: false, submitting: false }))
      .toBe('Сохранить как черновик');
  });
});
