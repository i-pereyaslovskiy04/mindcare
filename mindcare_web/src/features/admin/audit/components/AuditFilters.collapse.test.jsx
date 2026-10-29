import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import AuditFilters from './AuditFilters';
import { SOURCE_DEFAULTS, defaultCommon } from '../lib/auditFilters';

jest.mock('../../../../api/users.api');

const OPTIONS = {
  audit_events: ['admin_role_add'],
  auth_events: ['login'],
  actor_roles: ['admin', 'supervisor'],
  outcomes: ['success', 'failure'],
  entity_types: ['user', 'appointment'],
  tables: ['meeting_types'],
  operations: ['UPDATE'],
  actor_kinds: { audit_log: ['user', 'system'], auth_log: ['user'], data_change_log: ['user'] },
  auth_methods: ['password'],
};

function Harness({ initial = {}, setFiltersSpy = jest.fn(), source = 'audit_log' }) {
  const [filters, setFiltersState] = useState({ ...defaultCommon(7), ...SOURCE_DEFAULTS[source], ...initial });
  const setFilters = (patch) => { setFiltersSpy(patch); setFiltersState((prev) => ({ ...prev, ...patch })); };
  return (
    <AuditFilters
      source={source}
      defaultRangeDays={7}
      filters={filters}
      setFilters={setFilters}
      resetFilters={jest.fn()}
      options={OPTIONS}
      optionsError={null}
      onRetryOptions={jest.fn()}
      selectedActor={null}
      actorResetKey={0}
      onSelectActor={jest.fn()}
      onClearActor={jest.fn()}
    />
  );
}

const toggle = () => screen.getByRole('button', { name: /^Фильтры/ });

test('кнопка свёрнута по умолчанию и связана с панелью (aria-expanded, aria-controls)', () => {
  render(<Harness />);
  expect(toggle()).toHaveAttribute('aria-expanded', 'false');
  const panelId = toggle().getAttribute('aria-controls');
  // eslint-disable-next-line testing-library/no-node-access
  const panel = document.getElementById(panelId);
  expect(panel).not.toBeNull();
  expect(panel).toContainElement(screen.getByRole('button', { name: 'Сбросить фильтры' }));
});

test('без применённых фильтров — «Фильтры», с ними — «Фильтры · N» и понятное имя', () => {
  const { unmount } = render(<Harness />);
  expect(toggle()).toHaveTextContent(/^Фильтры$/);
  unmount();

  render(<Harness initial={{ outcome: 'failure' }} />);
  expect(toggle()).toHaveAccessibleName(/^Фильтры · 1 активный$/);
});

test('N считает только реальные фильтры: порядок и категория не считаются', () => {
  render(<Harness initial={{ order: 'asc', category: 'users', actorRole: 'admin', includeAccessEvents: true }} />);
  expect(toggle()).toHaveAccessibleName(/^Фильтры · 2 активных$/);
});

test('сворачивание не меняет значения и не вызывает setFilters (запросов нет)', () => {
  const spy = jest.fn();
  render(<Harness initial={{ outcome: 'failure' }} setFiltersSpy={spy} />);
  fireEvent.click(toggle());
  expect(toggle()).toHaveAttribute('aria-expanded', 'true');
  fireEvent.click(toggle());
  expect(toggle()).toHaveAttribute('aria-expanded', 'false');
  expect(spy).not.toHaveBeenCalled();
  expect(toggle()).toHaveAccessibleName(/^Фильтры · 1 активный$/);
});

test('состояние раскрытия переживает смену журнала (компонент не перемонтируется)', () => {
  const { rerender } = render(<Harness />);
  fireEvent.click(toggle());
  rerender(<Harness source="auth_log" />);
  expect(toggle()).toHaveAttribute('aria-expanded', 'true');
});
