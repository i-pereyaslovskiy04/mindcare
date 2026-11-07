import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RulesBuilder from './RulesBuilder';
import { emptyRules, toBackendRules } from '../lib/rulesShape';

let n = 0;
const nextKey = () => `k${++n}`;

function Harness({ questions, onValue }) {
  const [value, setValue] = useState(emptyRules());
  return (
    <RulesBuilder value={value} questions={questions} nextKey={nextKey}
      onChange={(v) => { setValue(v); onValue(v); }} />
  );
}

test('включение, шкалы из вопросов, предел достоверности и тип', () => {
  const onValue = jest.fn();
  render(<Harness questions={[{ scale: 'L' }, { scale: 'A' }, { scale: 'A' }]} onValue={onValue} />);
  userEvent.click(screen.getByRole('checkbox', { name: /Задать правила обработки/ }));
  userEvent.click(screen.getByRole('button', { name: /Добавить шкалы из вопросов \(L, A\)/ }));
  const limits = screen.getAllByLabelText('Предел достоверности');
  userEvent.type(limits[0], '5');
  expect(screen.getByLabelText('Пометка недостоверного результата')).toHaveValue('недостоверно');
  userEvent.click(screen.getByRole('button', { name: '+ Тип' }));
  userEvent.type(screen.getByLabelText('Название типа'), 'Тревожный');
  userEvent.type(screen.getByLabelText('Порог типа'), '8');

  const rules = toBackendRules(onValue.mock.calls.at(-1)[0]);
  expect(rules.scales.map((s) => s.code)).toEqual(['L', 'A']);
  expect(rules.validity).toEqual({ scales: [{ code: 'L', max_valid: 5 }], invalid_mark: 'недостоверно' });
  expect(rules.types).toBeNull();   // у типа ещё нет шкал
  expect(screen.queryByRole('button', { name: /Добавить шкалы из вопросов/ })).toBeNull();
});

test('удаление и перемещение шкалы', () => {
  const onValue = jest.fn();
  render(<Harness questions={[{ scale: 'A' }, { scale: 'B' }]} onValue={onValue} />);
  userEvent.click(screen.getByRole('checkbox', { name: /Задать правила обработки/ }));
  userEvent.click(screen.getByRole('button', { name: /Добавить шкалы из вопросов/ }));
  userEvent.click(screen.getByRole('button', { name: 'Выше: B' }));
  expect(toBackendRules(onValue.mock.calls.at(-1)[0]).scales.map((s) => s.code)).toEqual(['B', 'A']);
  userEvent.click(screen.getByRole('button', { name: 'Удалить шкалу A' }));
  expect(toBackendRules(onValue.mock.calls.at(-1)[0]).scales.map((s) => s.code)).toEqual(['B']);
});

test('свои уровни у основной шкалы', () => {
  const onValue = jest.fn();
  render(<Harness questions={[{ scale: 'A' }]} onValue={onValue} />);
  userEvent.click(screen.getByRole('checkbox', { name: /Задать правила обработки/ }));
  userEvent.click(screen.getByRole('button', { name: /Добавить шкалы из вопросов/ }));
  userEvent.click(screen.getByRole('checkbox', { name: 'Свои уровни' }));
  expect(screen.getByText(/Уровни шкалы «A» — вместо общих/)).toBeInTheDocument();
  const codes = screen.getAllByLabelText('Код (латиница)');
  userEvent.type(codes[0], 'norm');
  const rules = toBackendRules(onValue.mock.calls.at(-1)[0]);
  expect(rules.scales[0].levels).toEqual([{ code: 'norm', label: 'norm', min: 0, max: 0 }]);
  expect(rules.levels).toEqual([]);
});
