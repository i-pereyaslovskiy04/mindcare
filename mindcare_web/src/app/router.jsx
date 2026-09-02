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
import { PrivateRoute, RoleRoute, DashboardRedirect } from './guards';

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
import ThemePreviewPage  from '../pages/theme-preview/ThemePreviewPage';

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
import AdminTestsPage      from '../features/admin/tests/pages/AdminTestsPage';
import TestFormPage        from '../features/admin/tests/pages/TestFormPage';
import AdminSettingsPage   from '../features/admin/settings/pages/AdminSettingsPage';
import EmailDomainsPage    from '../features/admin/email-domains/pages/EmailDomainsPage';
import AuditLogsPage       from '../features/admin/audit/pages/AuditLogsPage';

// ── Student (role-specific dashboard) ─────────────────────────────────────────
import ClientDashboard      from '../pages/client/ClientDashboard';
import StudentHome          from '../pages/student/StudentHome';
import DiaryPage            from '../pages/student/DiaryPage';
import DiaryHistoryPage    from '../pages/student/DiaryHistoryPage';
import TestsPage            from '../pages/student/Tests/TestsPage';
import TestCatalogPage      from '../pages/student/Tests/TestCatalogPage';
import TestTakePage         from '../pages/student/Tests/TestTakePage';
import ResultsHistoryPage   from '../pages/student/Tests/ResultsHistoryPage';
import ResultDetailPage     from '../pages/student/Tests/ResultDetailPage';
import StudentMaterialsPage from '../pages/student/Materials/MaterialsPage';
import TasksPage            from '../pages/student/Tasks/TasksPage';
import ChatPage             from '../pages/student/Chat/ChatPage';
import CalendarPage              from '../pages/student/Calendar/CalendarPage';
import StudentGroupSessionsPage  from '../pages/student/GroupSessions/GroupSessionsPage';
import SettingsPage         from '../pages/student/Settings/SettingsPage';

// ── Psychologist ──────────────────────────────────────────────────────────────
import PsychologistLayout           from '../pages/psychologist/PsychologistLayout';
import PsychologistHome             from '../pages/psychologist/PsychologistHome';
import PsychologistStudentsPage     from '../pages/psychologist/PsychologistStudentsPage';
import PsychologistStudentCardPage  from '../pages/psychologist/PsychologistStudentCardPage';
import PsychologistChatPage         from '../pages/psychologist/Chat/PsychologistChatPage';
import PsychologistAppointmentsPage from '../pages/psychologist/Appointments/AppointmentsPage';
import PsychologistTestsPage        from '../pages/psychologist/Tests/PsychologistTestsPage';
import PsychologistTestFormPage     from '../pages/psychologist/Tests/PsychologistTestFormPage';

// ── Supervisor ────────────────────────────────────────────────────────────────
import SupervisorLayout    from '../pages/supervisor/SupervisorLayout';
import SupervisorHome      from '../pages/supervisor/SupervisorHome';
import EngagementsPage     from '../pages/supervisor/EngagementsPage';
import MeetingTypesPage    from '../pages/supervisor/MeetingTypesPage';
import BannerSlidesPage    from '../pages/supervisor/BannerSlidesPage';
import ServiceCardsPage    from '../pages/supervisor/ServiceCardsPage';
import GroupSessionsPage   from '../pages/supervisor/GroupSessionsPage';
import SchedulePage        from '../pages/supervisor/SchedulePage';
import BookingPage         from '../pages/supervisor/BookingPage';

// ── Shared cabinet pages ──────────────────────────────────────────────────────
import CabinetSettingsPage from '../components/CabinetLayout/CabinetSettingsPage';

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
      {process.env.NODE_ENV !== 'production' && (
        <Route path="/theme-preview" element={<ThemePreviewPage />} />
      )}

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
        <Route path="diary/history" element={<DiaryHistoryPage />} />
        <Route path="tests"                    element={<TestsPage />} />
        <Route path="tests/catalog"            element={<TestCatalogPage />} />
        <Route path="tests/catalog/:uuid"      element={<TestTakePage />} />
        <Route path="tests/results"            element={<ResultsHistoryPage />} />
        <Route path="tests/results/:uuid"      element={<ResultDetailPage />} />
        <Route path="materials"     element={<StudentMaterialsPage />} />
        <Route path="tasks"         element={<TasksPage />} />
        <Route path="chat"          element={<ChatPage />} />
        <Route path="calendar"        element={<CalendarPage />} />
        <Route path="group-sessions"  element={<StudentGroupSessionsPage />} />
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
        <Route path="appointments"          element={<PsychologistAppointmentsPage />} />
        <Route path="tests"                 element={<PsychologistTestsPage />} />
        <Route path="tests/new"             element={<PsychologistTestFormPage />} />
        <Route path="tests/:uuid"           element={<PsychologistTestFormPage />} />
        <Route path="chat"                  element={<PsychologistChatPage />} />
        <Route path="settings"              element={<CabinetSettingsPage cabinetRole="psychologist" />} />
      </Route>

      {/* Supervisor */}
      <Route
        path="/supervisor"
        element={<RoleRoute roles={['supervisor']}><SupervisorLayout /></RoleRoute>}
      >
        <Route index                          element={<SupervisorHome />} />
        <Route path="engagements"           element={<EngagementsPage />} />
        <Route path="meeting-types"         element={<MeetingTypesPage cabinetRole="supervisor" />} />
        <Route path="banner-slides"         element={<BannerSlidesPage cabinetRole="supervisor" />} />
        <Route path="service-cards"         element={<ServiceCardsPage cabinetRole="supervisor" />} />
        <Route path="tests"                 element={<AdminTestsPage cabinetRole="supervisor" />} />
        <Route path="tests/new"             element={<TestFormPage cabinetRole="supervisor" />} />
        <Route path="tests/:uuid"           element={<TestFormPage cabinetRole="supervisor" />} />
        <Route path="schedule"              element={<SchedulePage />} />
        <Route path="booking"               element={<BookingPage />} />
        <Route path="group-sessions"        element={<GroupSessionsPage />} />
        <Route path="settings"              element={<CabinetSettingsPage cabinetRole="supervisor" />} />
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
        <Route path="tests"        element={<AdminTestsPage />} />
        <Route path="tests/new"    element={<TestFormPage />} />
        <Route path="tests/:uuid"  element={<TestFormPage />} />
        <Route path="meeting-types" element={<MeetingTypesPage cabinetRole="admin" />} />
        <Route path="banner-slides" element={<BannerSlidesPage cabinetRole="admin" />} />
        <Route path="service-cards" element={<ServiceCardsPage cabinetRole="admin" />} />
        <Route path="email-domains" element={<EmailDomainsPage />} />
        <Route path="audit"        element={<AuditLogsPage />} />
        <Route path="settings"   element={<AdminSettingsPage />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
