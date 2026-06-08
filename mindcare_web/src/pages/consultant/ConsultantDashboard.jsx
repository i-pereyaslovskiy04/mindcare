import { useAuth, useLogout } from '../../features/auth/AuthContext';
import DashboardLayout from '../../components/layouts/DashboardLayout';

export default function ConsultantDashboard() {
  const { user } = useAuth();
  const logout = useLogout();

  return (
    <DashboardLayout>
      <h1>Кабинет специалиста</h1>
      <p>Добро пожаловать, <strong>{user?.name}</strong>!</p>
      <p>Роль: <code>{user?.role}</code></p>
      <button onClick={logout} style={{ marginTop: '2rem' }}>Выйти</button>
    </DashboardLayout>
  );
}
