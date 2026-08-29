/**
 * Route guards (ADR-018 multi-role). Вынесены из router.jsx отдельным модулем,
 * чтобы их можно было юнит-тестировать без загрузки всего дерева страниц
 * (router.jsx тянет тяжёлые модули вроде TiptapEditor).
 */
import { Navigate } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';
import RoleChooser from '../features/auth/RoleChooser';
import { getRoleHome } from '../shared/lib/routes';
import { normalizeRoles, selectableRoles } from '../shared/lib/roles';

/**
 * Requires authentication.
 * While auth state is resolving: render nothing (avoid flash).
 */
export function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/" state={{ openAuth: 'login' }} replace />;
  return children;
}

/**
 * Requires membership in one of the given roles (multi-role: пересечение с
 * user.roles, а не единственная legacy role). Mismatch → /profile.
 */
export function RoleRoute({ roles, children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/" state={{ openAuth: 'login' }} replace />;
  const userRoles = normalizeRoles(user);
  if (!roles.some((r) => userRoles.includes(r))) {
    return <Navigate to="/profile" replace />;
  }
  return children;
}

/**
 * /dashboard — редирект по активному/default кабинету (ADR-018):
 *   - 0 ролей → /profile;
 *   - валидный activeRole (по полному набору ролей) → его кабинет;
 *   - одна роль для выбора → её кабинет;
 *   - несколько ролей для выбора → RoleChooser.
 * activeRole валидируется по ПОЛНОМУ набору ролей (включая student), чтобы staff,
 * переключившийся в кабинет студента, не сбрасывался на reload. Выбор кабинета
 * (choices) считается по selectableRoles: у staff роль student скрыта, поэтому
 * [admin, student] не показывает одно-кнопочный RoleChooser, а сразу ведёт в /admin.
 */
export function DashboardRedirect() {
  const { user, loading, activeRole } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/" state={{ openAuth: 'login' }} replace />;

  const roles = normalizeRoles(user);
  if (roles.length === 0) return <Navigate to="/profile" replace />;
  if (activeRole && roles.includes(activeRole)) {
    return <Navigate to={getRoleHome(activeRole)} replace />;
  }
  const choices = selectableRoles(user);
  if (choices.length === 1) return <Navigate to={getRoleHome(choices[0])} replace />;
  return <RoleChooser roles={choices} />;
}
