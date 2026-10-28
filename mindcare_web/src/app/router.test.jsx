import fs from 'fs';
import path from 'path';
import { render, screen } from '@testing-library/react';
import {
  RoleRoute, DashboardRedirect, PrivateRoute, LegacyAuthRedirect, GuestOnly,
} from './guards';
import * as AuthContext from '../features/auth/AuthContext';

// react-router-dom (v7) не резолвится jest-резолвером в этом проекте — как и во
// всех существующих тестах, мокаем виртуально. Navigate рендерит свой `to`,
// чтобы можно было проверить цель редиректа.
// state и replace выводятся только если заданы — чтобы видеть router state
// редиректов на главную с AuthModal.
const mockLocation = { state: null };
jest.mock('react-router-dom', () => ({
  Navigate: ({ to, state, replace }) => (
    <div>
      NAV:{to}
      {state ? ` STATE:${JSON.stringify(state)}` : ''}
      {state && replace ? ' REPLACE' : ''}
    </div>
  ),
  useNavigate: () => jest.fn(),
  useLocation: () => mockLocation,
}), { virtual: true });
jest.mock('../features/auth/AuthContext', () => ({ useAuth: jest.fn() }));

function mockAuth(value) {
  AuthContext.useAuth.mockReturnValue({ loading: false, ...value });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockLocation.state = null;
});

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

// ── /auth/callback (Stage Social Auth 3B) ────────────────────────────────────

test('/auth/callback зарегистрирован ровно один раз и публичный', () => {
  const matches = ROUTER_SOURCE.match(/path="\/auth\/callback"/g) ?? [];
  expect(matches).toHaveLength(1);
  expect(ROUTER_SOURCE).toMatch(
    /<Route path="\/auth\/callback" element=\{<OAuthCallbackPage \/>\} \/>/,
  );
  // Не обёрнут guard'ом: ни PrivateRoute, ни RoleRoute в его element нет.
  const line = ROUTER_SOURCE.split(/\r?\n/).find((l) => l.includes('path="/auth/callback"'));
  expect(line).not.toMatch(/PrivateRoute|RoleRoute/);
});

test('страница callback импортируется из auth feature', () => {
  expect(ROUTER_SOURCE).toMatch(
    /import\s+OAuthCallbackPage\s+from\s+'\.\.\/features\/auth\/pages\/OAuthCallbackPage';/,
  );
});

// ── Канонический вход: главная + AuthModal ───────────────────────────────────

const LOGIN_MODAL = 'NAV:/ STATE:{"openAuth":"login"} REPLACE';
const REGISTER_MODAL = 'NAV:/ STATE:{"openAuth":"register"} REPLACE';

test.each([
  ['PrivateRoute', () => <PrivateRoute><div>SECRET</div></PrivateRoute>],
  ['RoleRoute', () => <RoleRoute roles={['student']}><div>SECRET</div></RoleRoute>],
  ['DashboardRedirect', () => <DashboardRedirect />],
])('%s без пользователя → главная + AuthModal «Вход» (не /login)', (_, ui) => {
  mockAuth({ user: null });
  render(ui());
  expect(screen.getByText(LOGIN_MODAL)).toBeInTheDocument();
  expect(screen.queryByText('SECRET')).toBeNull();
  expect(screen.queryByText(/NAV:\/login/)).toBeNull();
});

test('/login (совместимость) → replace на главную, вкладка «Вход»', () => {
  mockAuth({ user: null });
  render(<LegacyAuthRedirect tab="login" />);
  expect(screen.getByText(LOGIN_MODAL)).toBeInTheDocument();
});

test('/register (совместимость) → replace на главную, вкладка «Регистрация»', () => {
  mockAuth({ user: null });
  render(<LegacyAuthRedirect tab="register" />);
  expect(screen.getByText(REGISTER_MODAL)).toBeInTheDocument();
});

test('совместимый редирект пробрасывает только строковое сообщение и допустимый тон', () => {
  mockAuth({ user: null });
  mockLocation.state = { message: 'Сессия истекла. Войдите снова.' };
  const { unmount } = render(<LegacyAuthRedirect tab="login" />);
  expect(screen.getByText(
    'NAV:/ STATE:{"openAuth":"login","message":"Сессия истекла. Войдите снова.","messageTone":"info"} REPLACE',
  )).toBeInTheDocument();
  unmount();

  mockLocation.state = { message: 'Ошибка', messageTone: 'error' };
  const view = render(<LegacyAuthRedirect tab="login" />);
  expect(screen.getByText(
    'NAV:/ STATE:{"openAuth":"login","message":"Ошибка","messageTone":"error"} REPLACE',
  )).toBeInTheDocument();
  view.unmount();

  mockLocation.state = { message: 'Ошибка', messageTone: 'danger-class' };
  const utils = render(<LegacyAuthRedirect tab="login" />);
  expect(screen.getByText(
    'NAV:/ STATE:{"openAuth":"login","message":"Ошибка","messageTone":"info"} REPLACE',
  )).toBeInTheDocument();
  utils.unmount();

  mockLocation.state = { message: { html: '<b>x</b>' }, openAuth: 'admin' };
  render(<LegacyAuthRedirect tab="register" />);
  expect(screen.getByText(REGISTER_MODAL)).toBeInTheDocument();
});

test('совместимый редирект: вошедший пользователь идёт в кабинет, при загрузке — ничего', () => {
  mockAuth({ user: { roles: ['student'] } });
  const { unmount } = render(<LegacyAuthRedirect tab="login" />);
  expect(screen.getByText('NAV:/dashboard')).toBeInTheDocument();
  unmount();

  mockAuth({ user: null, loading: true });
  const { container } = render(<LegacyAuthRedirect tab="register" />);
  expect(container).toBeEmptyDOMElement();
});

test('/login и /register — совместимые редиректы, отдельных страниц входа нет', () => {
  expect(ROUTER_SOURCE).toMatch(
    /<Route path="\/login"\s+element=\{<LegacyAuthRedirect tab="login" \/>\} \/>/,
  );
  expect(ROUTER_SOURCE).toMatch(
    /<Route path="\/register"\s+element=\{<LegacyAuthRedirect tab="register" \/>\} \/>/,
  );
  expect(ROUTER_SOURCE.match(/path="\/login"/g)).toHaveLength(1);
  expect(ROUTER_SOURCE.match(/path="\/register"/g)).toHaveLength(1);
  expect(ROUTER_SOURCE).not.toMatch(/LoginPage|RegisterPage/);
  const pagesDir = path.join(__dirname, '..', 'features', 'auth', 'pages');
  expect(fs.existsSync(path.join(pagesDir, 'LoginPage.jsx'))).toBe(false);
  expect(fs.existsSync(path.join(pagesDir, 'RegisterPage.jsx'))).toBe(false);
});

// ── /register/confirm: кнопка «Продолжить регистрацию» из письма ─────────────

test('/register/confirm — главная с шагом подтверждения на том же адресе (без редиректа)', () => {
  expect(ROUTER_SOURCE).toMatch(
    /<Route path="\/register\/confirm" element=\{<GuestOnly><Home routeAuth="confirm" \/><\/GuestOnly>\} \/>/,
  );
  expect(ROUTER_SOURCE.match(/path="\/register\/confirm"/g)).toHaveLength(1);
  expect(ROUTER_SOURCE).not.toMatch(/LegacyAuthRedirect tab="confirm"/);
  // Ни параметров, ни query: email и код в адрес не попадают.
  expect(ROUTER_SOURCE).not.toMatch(/register\/confirm\/:|register\/confirm\?/);
});

test('GuestOnly: гостю — содержимое маршрута, без редиректа (адрес сохраняется)', () => {
  mockAuth({ user: null });
  render(<GuestOnly><div>CONFIRM_SCREEN</div></GuestOnly>);
  expect(screen.getByText('CONFIRM_SCREEN')).toBeInTheDocument();
  expect(screen.queryByText(/NAV:/)).toBeNull();
});

test('GuestOnly: при загрузке сессии содержимое остаётся, без редиректа', () => {
  mockAuth({ user: null, loading: true });
  render(<GuestOnly><div>CONFIRM_SCREEN</div></GuestOnly>);
  expect(screen.getByText('CONFIRM_SCREEN')).toBeInTheDocument();
});

test('GuestOnly: вошедший пользователь → кабинет', () => {
  mockAuth({ user: { roles: ['student'] } });
  render(<GuestOnly><div>CONFIRM_SCREEN</div></GuestOnly>);
  expect(screen.getByText('NAV:/dashboard')).toBeInTheDocument();
  expect(screen.queryByText('CONFIRM_SCREEN')).toBeNull();
});

test('/register/social — главная с продолжением регистрации через провайдера, без секретов в адресе', () => {
  expect(ROUTER_SOURCE).toMatch(
    /<Route path="\/register\/social" element=\{<GuestOnly><Home routeAuth="social" \/><\/GuestOnly>\} \/>/,
  );
  expect(ROUTER_SOURCE.match(/path="\/register\/social"/g)).toHaveLength(1);
  expect(ROUTER_SOURCE).not.toMatch(/register\/social\/:|register\/social\?/);
});

// ── Библиотека материалов в кабинетах ────────────────────────────────────────

/** Блок role-Route кабинета: от `path="/<cabinet>"` до его закрывающего `</Route>`. */
function cabinetRouteBlock(cabinet) {
  const start = ROUTER_SOURCE.indexOf(`path="/${cabinet}"`);
  expect(start).toBeGreaterThan(-1);
  const end = ROUTER_SOURCE.indexOf('</Route>', start);
  expect(end).toBeGreaterThan(start);
  return ROUTER_SOURCE.slice(start, end);
}

test('материалы студента: список и чтение внутри student-кабинета', () => {
  const block = cabinetRouteBlock('student');
  expect(block).toMatch(/element=\{<RoleRoute roles=\{\['student'\]\}>/);
  expect(block).toMatch(/path="materials"\s+element=\{<StudentMaterialsPage \/>\}/);
  expect(block).toMatch(/path="materials\/:id"\s+element=\{<StudentMaterialItemPage \/>\}/);
});

test('материалы психолога: список и чтение внутри psychologist-кабинета', () => {
  const block = cabinetRouteBlock('psychologist');
  expect(block).toMatch(/element=\{<RoleRoute roles=\{\['psychologist'\]\}>/);
  expect(block).toMatch(/path="materials"\s+element=\{<PsychologistMaterialsPage \/>\}/);
  expect(block).toMatch(/path="materials\/:id"\s+element=\{<PsychologistMaterialItemPage \/>\}/);
});

test('публичная библиотека сохраняет свои маршруты', () => {
  expect(ROUTER_SOURCE).toMatch(/<Route path="\/materials"\s+element=\{<MaterialsPage \/>\} \/>/);
  expect(ROUTER_SOURCE).toMatch(/<Route path="\/materials\/:id" element=\{<MaterialsItemPage \/>\} \/>/);
});

// ── Модерация материалов психологов (ADR-034) ────────────────────────────────

test('модерация материалов: админ — очередь, супервизор — очередь и свои материалы', () => {
  expect(ROUTER_SOURCE).toMatch(
    /import\s+MaterialsReviewPage\s+from\s+'\.\.\/features\/materials\/pages\/MaterialsReviewPage';/,
  );
  expect(ROUTER_SOURCE).toMatch(
    /import\s+SupervisorMaterialsPage\s+from\s+'\.\.\/features\/materials\/pages\/SupervisorMaterialsPage';/,
  );
  const supervisor = cabinetRouteBlock('supervisor');
  expect(supervisor).toMatch(/path="materials"\s+element=\{<SupervisorMaterialsPage \/>\}/);
  expect(adminRouteBlock()).toMatch(/path="materials-review" element=\{<MaterialsReviewPage \/>\}/);
  // психолог страницу модерации не получает
  expect(cabinetRouteBlock('psychologist')).not.toContain('MaterialsReviewPage');
  expect(cabinetRouteBlock('psychologist')).not.toContain('SupervisorMaterialsPage');
});
