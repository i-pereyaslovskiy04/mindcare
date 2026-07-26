/**
 * Route guards (ADR-018 multi-role). Вынесены из router.jsx отдельным модулем,
 * чтобы их можно было юнит-тестировать без загрузки всего дерева страниц
 * (router.jsx тянет тяжёлые модули вроде TiptapEditor).
 */
import { Navigate } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';
import RoleChooser from '../features/auth/RoleChooser';
import { getRoleHome } from '../shared/lib/routes';
import { normalizeRoles } from '../shared/lib/roles';

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
 *   - 1 роль → её кабинет;
 *   - несколько + валидный activeRole → его кабинет;
 *   - несколько без валидного activeRole → RoleChooser.
 * activeRole всегда валидируется по membership.
 */
export function DashboardRedirect() {
  const { user, loading, activeRole } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/" state={{ openAuth: 'login' }} replace />;

  const roles = normalizeRoles(user);
  if (roles.length === 0) return <Navigate to="/profile" replace />;
  if (roles.length === 1) return <Navigate to={getRoleHome(roles[0])} replace />;
  if (activeRole && roles.includes(activeRole)) {
    return <Navigate to={getRoleHome(activeRole)} replace />;
  }
  return <RoleChooser roles={roles} />;
}
