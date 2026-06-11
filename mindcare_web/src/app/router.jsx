/**
 * router.jsx — application route tree.
 *
 * Route guards:
 *   <PrivateRoute>   — requires authentication, redirects to / (with login modal) when unauthenticated.
 *   <RoleRoute>      — requires specific role(s), redirects to /profile on mismatch.
 *
 * Public routes: /, /about, /services, /news, /materials, /login, /register, /health
 * Private routes: /dashboard, /profile
 * Role routes:   /student/*, /psychologist/*, /supervisor/*, /admin/*
 */

import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';
import { getRoleHome } from '../shared/lib/routes';

// ── Public pages ──────────────────────────────────────────────────────────────
import Home              from '../pages/home/Home';
import About             from '../pages/about/About';
import Services          from '../pages/services/Services';
import NewsPage          from '../pages/news/NewsPage';
import NewsItemPage      from '../pages/news/NewsItemPage';
import MaterialsPage     from '../pages/materials/MaterialsPage';
import MaterialsItemPage from '../pages/materials/MaterialsItemPage';
import NotFound          from '../pages/not-found/NotFound';
import HealthPage        from '../pages/health/HealthPage';

// ── Auth pages ────────────────────────────────────────────────────────────────
import LoginPage    from '../features/auth/pages/LoginPage';
import RegisterPage from '../features/auth/pages/RegisterPage';

// ── Profile ───────────────────────────────────────────────────────────────────
import ProfilePage from '../features/profile/pages/ProfilePage';

// ── Admin ─────────────────────────────────────────────────────────────────────
import AdminLayout    from '../features/admin/AdminLayout';
import UsersPage      from '../features/admin/users/pages/UsersPage';
import TagsPage       from '../features/admin/tags/pages/TagsPage';
import AdminNewsPage  from '../features/admin/news/pages/NewsPage';
import AdminArticlesPage   from '../features/admin/articles/pages/ArticlesPage';
import AdminCategoriesPage from '../features/admin/categories/pages/CategoriesPage';

// ── Student (role-specific dashboard) ─────────────────────────────────────────
import ClientDashboard      from '../pages/client/ClientDashboard';
import StudentHome          from '../pages/student/StudentHome';
import DiaryPage            from '../pages/student/DiaryPage';
import TestsPage            from '../pages/student/Tests/TestsPage';
import StudentMaterialsPage from '../pages/student/Materials/MaterialsPage';
import TasksPage            from '../pages/student/Tasks/TasksPage';
import ChatPage             from '../pages/student/Chat/ChatPage';
import CalendarPage         from '../pages/student/Calendar/CalendarPage';
import SettingsPage         from '../pages/student/Settings/SettingsPage';

// ── Psychologist ──────────────────────────────────────────────────────────────
import PsychologistLayout          from '../pages/psychologist/PsychologistLayout';
import PsychologistHome            from '../pages/psychologist/PsychologistHome';
import PsychologistStudentsPage    from '../pages/psychologist/PsychologistStudentsPage';
import PsychologistStudentCardPage from '../pages/psychologist/PsychologistStudentCardPage';

// ── Supervisor ────────────────────────────────────────────────────────────────
import SupervisorLayout    from '../pages/supervisor/SupervisorLayout';
import SupervisorHome      from '../pages/supervisor/SupervisorHome';
import EngagementsPage     from '../pages/supervisor/EngagementsPage';

// ── Shared cabinet pages ──────────────────────────────────────────────────────
import CabinetSettingsPage from '../components/CabinetLayout/CabinetSettingsPage';

// ── Route guards ──────────────────────────────────────────────────────────────

/**
 * Requires authentication.
 * While auth state is resolving: render nothing (avoid flash).
 * If not authenticated: redirect to /login.
 */
function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user)   return <Navigate to="/" state={{ openAuth: 'login' }} replace />;
  return children;
}

/**
 * Requires one of the given roles.
 * Falls back to /profile on role mismatch (user is authenticated but wrong role).
 */
function RoleRoute({ roles, children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user)                        return <Navigate to="/" state={{ openAuth: 'login' }} replace />;
  if (!roles.includes(user.role))   return <Navigate to="/profile" replace />;
  return children;
}

/**
 * /dashboard — smart redirect to the role-specific home page.
 */
function DashboardRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user)   return <Navigate to="/" state={{ openAuth: 'login' }} replace />;

  return <Navigate to={getRoleHome(user.role)} replace />;
}

// ── Route tree ────────────────────────────────────────────────────────────────

export default function AppRouter() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/"              element={<Home />} />
      <Route path="/about"         element={<About />} />
      <Route path="/services"      element={<Services />} />
      <Route path="/news"          element={<NewsPage />} />
      <Route path="/news/:id"      element={<NewsItemPage />} />
      <Route path="/materials"     element={<MaterialsPage />} />
      <Route path="/materials/:id" element={<MaterialsItemPage />} />
      <Route path="/health"        element={<HealthPage />} />

      {/* Auth */}
      <Route path="/login"    element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Private — any authenticated user */}
      <Route path="/dashboard" element={<PrivateRoute><DashboardRedirect /></PrivateRoute>} />
      <Route path="/profile"   element={<PrivateRoute><ProfilePage /></PrivateRoute>} />

      {/* Student */}
      <Route
        path="/student"
        element={<RoleRoute roles={['student']}><ClientDashboard /></RoleRoute>}
      >
        <Route index                element={<StudentHome />} />
        <Route path="diary"         element={<DiaryPage />} />
        <Route path="tests"         element={<TestsPage />} />
        <Route path="materials"     element={<StudentMaterialsPage />} />
        <Route path="tasks"         element={<TasksPage />} />
        <Route path="chat"          element={<ChatPage />} />
        <Route path="calendar"      element={<CalendarPage />} />
        <Route path="settings"      element={<SettingsPage />} />
      </Route>

      {/* Psychologist */}
      <Route
        path="/psychologist"
        element={<RoleRoute roles={['psychologist']}><PsychologistLayout /></RoleRoute>}
      >
        <Route index                          element={<PsychologistHome />} />
        <Route path="students"              element={<PsychologistStudentsPage />} />
        <Route path="students/:studentId"   element={<PsychologistStudentCardPage />} />
        <Route path="settings"              element={<CabinetSettingsPage />} />
      </Route>

      {/* Supervisor */}
      <Route
        path="/supervisor"
        element={<RoleRoute roles={['supervisor']}><SupervisorLayout /></RoleRoute>}
      >
        <Route index                  element={<SupervisorHome />} />
        <Route path="engagements"     element={<EngagementsPage />} />
        <Route path="settings"        element={<CabinetSettingsPage />} />
      </Route>

      {/* Admin */}
      <Route
        path="/admin"
        element={<RoleRoute roles={['admin']}><AdminLayout /></RoleRoute>}
      >
        <Route index              element={<Navigate to="users" replace />} />
        <Route path="users"      element={<UsersPage />} />
        <Route path="tags"       element={<TagsPage />} />
        <Route path="news"       element={<AdminNewsPage />} />
        <Route path="articles"   element={<AdminArticlesPage />} />
        <Route path="categories" element={<AdminCategoriesPage />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
