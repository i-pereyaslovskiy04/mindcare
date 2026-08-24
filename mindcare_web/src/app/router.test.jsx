import fs from 'fs';
import path from 'path';
import { render, screen } from '@testing-library/react';
import { RoleRoute, DashboardRedirect } from './guards';
import * as AuthContext from '../features/auth/AuthContext';

// react-router-dom (v7) не резолвится jest-резолвером в этом проекте — как и во
// всех существующих тестах, мокаем виртуально. Navigate рендерит свой `to`,
// чтобы можно было проверить цель редиректа.
jest.mock('react-router-dom', () => ({
  Navigate: ({ to }) => <div>NAV:{to}</div>,
  useNavigate: () => jest.fn(),
}), { virtual: true });
jest.mock('../features/auth/AuthContext', () => ({ useAuth: jest.fn() }));

function mockAuth(value) {
  AuthContext.useAuth.mockReturnValue({ loading: false, ...value });
}

beforeEach(() => jest.clearAllMocks());

// ── RoleRoute ────────────────────────────────────────────────────────────────

test('RoleRoute grants access when a membership role intersects allowed', () => {
  mockAuth({ user: { roles: ['admin', 'supervisor', 'psychologist'] } });
  render(<RoleRoute roles={['admin']}><div>GRANTED</div></RoleRoute>);
  expect(screen.getByText('GRANTED')).toBeInTheDocument();
});

test('RoleRoute grants supervisor+psychologist to a psychologist route', () => {
  mockAuth({ user: { roles: ['supervisor', 'psychologist'] } });
  render(<RoleRoute roles={['psychologist']}><div>GRANTED</div></RoleRoute>);
  expect(screen.getByText('GRANTED')).toBeInTheDocument();
});

test('RoleRoute redirects to /profile without membership', () => {
  mockAuth({ user: { roles: ['supervisor', 'psychologist'] } });
  render(<RoleRoute roles={['admin']}><div>GRANTED</div></RoleRoute>);
  expect(screen.getByText('NAV:/profile')).toBeInTheDocument();
  expect(screen.queryByText('GRANTED')).toBeNull();
});

// ── DashboardRedirect ────────────────────────────────────────────────────────

test('single role redirects straight to its cabinet', () => {
  mockAuth({ user: { roles: ['psychologist'] }, activeRole: null });
  render(<DashboardRedirect />);
  expect(screen.getByText('NAV:/psychologist')).toBeInTheDocument();
});

test('multi-role with valid activeRole redirects to that cabinet', () => {
  mockAuth({ user: { roles: ['admin', 'supervisor'] }, activeRole: 'supervisor' });
  render(<DashboardRedirect />);
  expect(screen.getByText('NAV:/supervisor')).toBeInTheDocument();
});

test('multi-role without valid activeRole shows the cabinet chooser', () => {
  mockAuth({ user: { roles: ['admin', 'supervisor'] }, activeRole: null });
  render(<DashboardRedirect />);
  expect(screen.getByText('Выберите кабинет')).toBeInTheDocument();
});

test('multi-role with an invalid stored activeRole falls back to chooser', () => {
  mockAuth({ user: { roles: ['supervisor', 'psychologist'] }, activeRole: 'admin' });
  render(<DashboardRedirect />);
  expect(screen.getByText('Выберите кабинет')).toBeInTheDocument();
});

test('no roles redirects to /profile', () => {
  mockAuth({ user: { roles: [] }, activeRole: null });
  render(<DashboardRedirect />);
  expect(screen.getByText('NAV:/profile')).toBeInTheDocument();
});

// ── Дерево маршрутов ─────────────────────────────────────────────────────────
//
// Проверяется по исходнику, а не рендером <AppRouter />. Причина зафиксирована
// в самом router.jsx (см. guards.jsx: «router.jsx тянет тяжёлые модули вроде
// TiptapEditor»): импорт файла подтянул бы @tiptap/react — ESM-пакет вне
// transformIgnorePatterns CRA — и десятки страниц. Структурная проверка даёт
// тот же ответ детерминированно и без побочных импортов.

const ROUTER_SOURCE = fs.readFileSync(
  path.join(__dirname, 'router.jsx'),
  'utf8',
);

/** Блок admin-Route: от `path="/admin"` до закрывающего его `</Route>`. */
function adminRouteBlock() {
  const start = ROUTER_SOURCE.indexOf('path="/admin"');
  expect(start).toBeGreaterThan(-1);
  const end = ROUTER_SOURCE.indexOf('</Route>', start);
  expect(end).toBeGreaterThan(start);
  return ROUTER_SOURCE.slice(start, end);
}

test('audit page is imported from its feature module', () => {
  expect(ROUTER_SOURCE).toMatch(
    /import\s+AuditLogsPage\s+from\s+'\.\.\/features\/admin\/audit\/pages\/AuditLogsPage';/,
  );
});

test('/admin/audit is registered exactly once', () => {
  const matches = ROUTER_SOURCE.match(/path="audit"/g) ?? [];
  expect(matches).toHaveLength(1);
});

test('/admin/audit lives inside the admin RoleRoute and nowhere else', () => {
  const block = adminRouteBlock();

  // Родительский маршрут защищён именно ролью admin.
  expect(block).toMatch(/element=\{<RoleRoute roles=\{\['admin'\]\}>/);
  // Дочерний маршрут — внутри этого блока.
  expect(block).toMatch(/path="audit"\s+element=\{<AuditLogsPage \/>\}/);

  // За пределами admin-блока маршрута нет.
  const outside = ROUTER_SOURCE.replace(block, '');
  expect(outside).not.toContain('path="audit"');
});
