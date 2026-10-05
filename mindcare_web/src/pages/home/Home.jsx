import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';
import Navbar from '../../components/Navbar/Navbar';
import Hero from './components/Hero';
import QuickActions from './components/QuickActions';
import NewsSection from '../../features/news/components/NewsSection';
import Footer from '../../components/Footer/Footer';
import AuthModal from '../../features/auth/ui/AuthModal';
import CookieBanner from '../../components/CookieBanner/CookieBanner';
import { authRequestFrom } from '../../features/auth/lib/authEntry';

// Router-state контракт ({ openAuth, message?, messageTone? }) и его
// валидация — features/auth/lib/authEntry.js. Пишут его guards, истечение
// сессии, смена пароля, совместимые /login и /register и терминальные ошибки
// OAuth callback.
const CLOSED = { open: false, tab: 'login', message: '', messageTone: 'info' };

export default function Home() {
  const location = useLocation();
  const { loading, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const request = authRequestFrom(location.state);

  const [auth, setAuth] = useState(() => (request ? { open: true, ...request } : CLOSED));

  // Новая навигация с openAuth, когда Home уже смонтирован (например, guard
  // вернул на `/` с открытой главной): применяется во время рендера по ключу
  // записи истории — без устаревшей вкладки и без лишнего кадра.
  const [handledKey, setHandledKey] = useState(location.key);
  if (request && handledKey !== location.key) {
    setHandledKey(location.key);
    setAuth({ open: true, ...request });
  }

  // Router state одноразовый: очищаем его через роутер (replace), чтобы
  // «назад»/обновление страницы не открывали модалку повторно. После очистки
  // request === null, поэтому эффект не зацикливается.
  const hasRequest = request !== null;
  useEffect(() => {
    if (!hasRequest) return;
    navigate(`${location.pathname}${location.search}`, { replace: true, state: null });
  }, [hasRequest, location.key, location.pathname, location.search, navigate]);

  const handleOpenAuth = () => {
    if (isAuthenticated) return;
    // Navbar: всегда «Вход» и без прежнего системного сообщения.
    setAuth({ ...CLOSED, open: true });
  };
  const handleCloseAuth = () => {
    // Закрытие сбрасывает сообщение и тон — при следующем открытии их нет.
    setAuth((prev) => ({ ...CLOSED, tab: prev.tab }));
  };
  // Кабинет выбирает DashboardRedirect (multi-role: chooser/activeRole).
  const handleGoToDashboard = () => navigate('/dashboard');

  return (
    <>
      <Navbar onOpenAuth={handleOpenAuth} />
      <Hero />
      {!loading && isAuthenticated && (
        <QuickActions onGoToDashboard={handleGoToDashboard} />
      )}
      <NewsSection />
      <Footer />
      {!loading && !isAuthenticated && (
        <AuthModal
          isOpen={auth.open}
          initialTab={auth.tab}
          onClose={handleCloseAuth}
          message={auth.message}
          messageTone={auth.messageTone}
        />
      )}
      <CookieBanner />
    </>
  );
}
