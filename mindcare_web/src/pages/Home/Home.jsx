import { useSelector, useDispatch } from "react-redux";
import { logout } from "../../store/authSlice";
import { useNavigate } from "react-router-dom";
import styles from "./Home.module.css";

export default function Home() {
  const { user } = useSelector((s) => s.auth);
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const handleLogout = () => {
    dispatch(logout());
    navigate("/login");
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <span className={styles.logo}>MindCare</span>
        <div className={styles.headerRight}>
          <span className={styles.userName}>{user?.name}</span>
          <button className={styles.logoutBtn} onClick={handleLogout}>Выйти</button>
        </div>
      </header>

      <main className={styles.main}>
        <h1 className={styles.welcome}>Добро пожаловать, {user?.name}!</h1>
        <p className={styles.roleLabel}>Роль: <strong>{roleLabel(user?.role)}</strong></p>

        <div className={styles.cards}>
          {menuItems(user?.role).map((item) => (
            <div key={item.title} className={styles.card}>
              <div className={styles.cardIcon}>{item.icon}</div>
              <h3>{item.title}</h3>
              <p>{item.desc}</p>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}

function roleLabel(role) {
  return { patient: "Пациент", psychologist: "Психолог", admin: "Администратор" }[role] ?? role;
}

function menuItems(role) {
  const all = {
    patient: [
      { icon: "🧠", title: "Психологические тесты", desc: "Пройдите тесты и узнайте своё состояние" },
      { icon: "💬", title: "Чат с психологом", desc: "Общайтесь со специалистом онлайн" },
      { icon: "📚", title: "Статьи", desc: "Полезные материалы о ментальном здоровье" },
      { icon: "📅", title: "Запись на приём", desc: "Запишитесь к психологу" },
    ],
    psychologist: [
      { icon: "👥", title: "Мои пациенты", desc: "Список ваших пациентов" },
      { icon: "💬", title: "Сообщения", desc: "Переписка с пациентами" },
      { icon: "📅", title: "Расписание", desc: "Управление записями на приём" },
      { icon: "📝", title: "Заметки", desc: "Ваши профессиональные заметки" },
    ],
    admin: [
      { icon: "👤", title: "Пользователи", desc: "Управление всеми аккаунтами" },
      { icon: "🧠", title: "Тесты", desc: "Создание и редактирование тестов" },
      { icon: "📚", title: "Статьи", desc: "Управление контентом" },
      { icon: "📊", title: "Статистика", desc: "Общая аналитика платформы" },
    ],
  };
  return all[role] ?? [];
}
