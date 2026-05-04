import { useAuth } from '../../features/auth/AuthContext';
import DashboardLayout from '../../components/layouts/DashboardLayout';

export default function ConsultantDashboard() {
  const { user, logout } = useAuth();

  return (
    <DashboardLayout>
      <h1>Кабинет специалиста</h1>
      <p>Добро пожаловать, <strong>{user?.name}</strong>!</p>
      <p>Роль: <code>{user?.role}</code></p>
      <button onClick={logout} style={{ marginTop: '2rem' }}>Выйти</button>
    </DashboardLayout>
  );
}
