import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';

import Home from '../pages/home/Home';
import About from '../pages/about/About';
import Services from '../pages/services/Services';
import NewsPage from '../pages/news/NewsPage';
import NewsItemPage from '../pages/news/NewsItemPage';
import MaterialsPage from '../pages/materials/MaterialsPage';
import MaterialsItemPage from '../pages/materials/MaterialsItemPage';
import NotFound from '../pages/not-found/NotFound';

import ClientDashboard from '../pages/client/ClientDashboard';
import ConsultantDashboard from '../pages/consultant/ConsultantDashboard';
import AdminDashboard from '../pages/admin/AdminDashboard';
import StudentHome from '../pages/student/StudentHome';
import DiaryPage from '../pages/student/DiaryPage';
import TestsPage from '../pages/student/Tests/TestsPage';
import StudentMaterialsPage from '../pages/student/Materials/MaterialsPage';
import TasksPage from '../pages/student/Tasks/TasksPage';
import ChatPage from '../pages/student/Chat/ChatPage';
import CalendarPage from '../pages/student/Calendar/CalendarPage';

function ProtectedRoute({ roles, children }) {
  const { user, loading } = useAuth();

  if (loading) return null;
  if (!user) return <Navigate to="/" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;

  return children;
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/about" element={<About />} />
      <Route path="/services" element={<Services />} />
      <Route path="/news" element={<NewsPage />} />
      <Route path="/news/:id" element={<NewsItemPage />} />
      <Route path="/materials" element={<MaterialsPage />} />
      <Route path="/materials/:id" element={<MaterialsItemPage />} />

      <Route
        path="/student"
        element={
          <ProtectedRoute roles={['student']}>
            <ClientDashboard />
          </ProtectedRoute>
        }
      >
        <Route index element={<StudentHome />} />
        <Route path="diary" element={<DiaryPage />} />
        <Route path="tests" element={<TestsPage />} />
        <Route path="materials" element={<StudentMaterialsPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="calendar" element={<CalendarPage />} />
      </Route>
      <Route
        path="/psychologist"
        element={
          <ProtectedRoute roles={['psychologist']}>
            <ConsultantDashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin"
        element={
          <ProtectedRoute roles={['admin']}>
            <AdminDashboard />
          </ProtectedRoute>
        }
      />

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
