import { useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import styles from "./Landing.module.css";

export default function Landing() {
  const navigate = useNavigate();
  const { user } = useSelector((s) => s.auth);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.logo}>MindCare</span>
          <span className={styles.headerUniv}>ДонГУ</span>
        </div>
        <button className={styles.btnPrimary} onClick={() => navigate(user ? "/dashboard" : "/login")}>
          {user ? "Личный кабинет" : "Войти"}
        </button>
      </header>

      {/* Hero */}
      <section className={styles.hero}>
        <div className={styles.heroText}>
          <span className={styles.badge}>Донецкий Государственный Университет</span>
          <h1>Пространство для<br />вашего спокойствия</h1>
          <p>Официальная платформа психологической помощи ДонГУ для студентов, сотрудников и жителей Донецка. Бесплатно. Конфиденциально.</p>
          <button className={styles.btnHero} onClick={() => navigate(user ? "/dashboard" : "/login")}>
            {user ? "Перейти в кабинет" : "Начать бесплатно"}
          </button>
        </div>
        <div className={styles.heroVisual}>
          <div className={styles.blob} />
          <div className={styles.floatCard}>
            <span>🌿</span>
            <div>
              <strong>Для всех и каждого</strong>
              <p>Студенты · Сотрудники · Жители</p>
            </div>
          </div>
        </div>
      </section>

      {/* Tracking section */}
      <section className={styles.trackSection}>
        <div className={styles.trackInner}>
          <div className={styles.trackText}>
            <p className={styles.sectionLabel}>Мониторинг состояния</p>
            <h2>Следите за своим психологическим состоянием</h2>
            <p>Регулярные тесты и персональная аналитика помогут вам понять динамику настроения, вовремя заметить тревожные сигналы и принять меры до того, как стресс станет проблемой.</p>
            <ul className={styles.trackList}>
              <li><span>📈</span> График изменения вашего состояния по времени</li>
              <li><span>🔔</span> Уведомления при отклонении от нормы</li>
              <li><span>🧩</span> Персональные рекомендации по результатам тестов</li>
              <li><span>🔒</span> Данные доступны только вам и вашему психологу</li>
            </ul>
          </div>
          <div className={styles.trackVisual}>
            <div className={styles.chartCard}>
              <p className={styles.chartTitle}>Ваше состояние за месяц</p>
              <div className={styles.chartBars}>
                {[60, 45, 70, 55, 80, 65, 75, 50, 85, 70, 90, 78].map((h, i) => (
                  <div key={i} className={styles.bar} style={{ height: `${h}%` }} />
                ))}
              </div>
              <div className={styles.chartLabels}>
                <span>Тревога снижается</span>
                <span className={styles.chartGood}>↑ +24%</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className={styles.featuresSection}>
        <p className={styles.sectionLabel}>Возможности платформы</p>
        <h2 className={styles.sectionTitle}>Всё что нужно — в одном месте</h2>
        <div className={styles.features}>
          {FEATURES.map((f) => (
            <div key={f.title} className={styles.featureCard}>
              <div className={styles.featureTop}>
                <div className={styles.featureIcon}>{f.icon}</div>
                <span className={styles.featureNum}>{f.num}</span>
              </div>
              <h3>{f.title}</h3>
              <p>{f.desc}</p>
              <div className={styles.featureLine} />
            </div>
          ))}
        </div>
      </section>

      {/* University */}
      <section className={styles.univSection}>
        <div className={styles.univInner}>
          <div className={styles.univText}>
            <p className={styles.sectionLabelLight}>Для кого эта платформа</p>
            <h2>Открыта для каждого</h2>
            <p>MindCare — официальный проект Донецкого Государственного Университета. Мы верим, что психологическая помощь должна быть доступна всем.</p>
          </div>
          <div className={styles.audiences}>
            {AUDIENCES.map((a) => (
              <div key={a.title} className={styles.audienceCard}>
                <span>{a.icon}</span>
                <strong>{a.title}</strong>
                <p>{a.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className={styles.footer}>
        <span className={styles.footerLogo}>MindCare</span>
        <span>© 2025 Донецкий Государственный Университет — платформа психологической помощи</span>
      </footer>
    </div>
  );
}

const FEATURES = [
  { num: "01", icon: "🧪", title: "Психологические тесты", desc: "Научно обоснованные тесты для оценки эмоционального состояния, уровня тревоги и стресса." },
  { num: "02", icon: "💬", title: "Чат с психологом", desc: "Личная переписка с квалифицированным специалистом в безопасном пространстве." },
  { num: "03", icon: "📚", title: "Статьи и материалы", desc: "Полезный контент о ментальном здоровье, выгорании, тревоге и отношениях." },
  { num: "04", icon: "📅", title: "Запись на приём", desc: "Выберите психолога и запишитесь онлайн в удобное время." },
];

const AUDIENCES = [
  { icon: "🎓", title: "Студенты", desc: "Помощь во время сессий, адаптации и учебного стресса" },
  { icon: "👩‍💼", title: "Сотрудники", desc: "Поддержка при профессиональном выгорании и рабочих трудностях" },
  { icon: "🏙️", title: "Жители Донецка", desc: "Открытая платформа для всех, кто нуждается в поддержке" },
];
