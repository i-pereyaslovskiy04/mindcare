import {
  emptyRules, fromBackendRules, missingScaleCodes, snapshotRules, toBackendRules,
} from './rulesShape';

let n = 0;
const nextKey = () => `k${++n}`;

const ITO_LIKE = {
  version: 1,
  instruction: 'Отвечайте честно',
  scales: [
    { code: 'L', label: 'L Ложь', main: false },
    { code: 'I', label: 'I Экстраверсия', main: true },
  ],
  levels: [
    { code: 'low', label: 'Низкий', min: 0, max: 2 },
    { code: 'high', label: 'Высокий', min: 3, max: 9 },
  ],
  validity: { scales: [{ code: 'L', max_valid: 5 }], invalid_mark: 'недостоверно' },
  types: { threshold: 8, items: [{ name: 'Экстраверт', scales: ['I'] }] },
};

test('без правил — null', () => {
  expect(toBackendRules(emptyRules())).toBeNull();
  expect(fromBackendRules(null, nextKey).enabled).toBe(false);
});

test('туда-обратно без потерь', () => {
  const form = fromBackendRules(ITO_LIKE, nextKey);
  expect(form.scales[0].max_valid).toBe('5');
  expect(form.scales[1].max_valid).toBe('');
  expect(toBackendRules(form)).toEqual(ITO_LIKE);
});

test('пустые строки отбрасываются, блоки без данных — null', () => {
  const form = {
    ...emptyRules(),
    enabled: true,
    scales: [{ _key: 'a', code: ' A ', label: '', main: true, max_valid: '' },
      { _key: 'b', code: '', label: 'пусто', main: false, max_valid: '' }],
    types: [{ _key: 't', name: 'Без шкал', scales: [] }],
  };
  expect(toBackendRules(form)).toEqual({
    version: 1, instruction: null,
    scales: [{ code: 'A', label: 'A', main: true }],
    levels: [], validity: null, types: null,
  });
});

test('снимок стабилен для одинаковых правил', () => {
  expect(snapshotRules(fromBackendRules(ITO_LIKE, nextKey)))
    .toBe(snapshotRules(fromBackendRules(ITO_LIKE, nextKey)));
});

test('шкалы из вопросов, которых нет в правилах', () => {
  const form = fromBackendRules(ITO_LIKE, nextKey);
  const questions = [{ scale: 'I' }, { scale: 'II' }, { scale: ' II ' }, { scale: '' }, { scale: 'F' }];
  expect(missingScaleCodes(form, questions)).toEqual(['II', 'F']);
});
