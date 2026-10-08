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
import { authEntryState, authRequestFrom } from '../../features/auth/lib/authEntry';

// Router-state контракт ({ openAuth, message?, messageTone? }) и его
// валидация — features/auth/lib/authEntry.js. Пишут его guards, истечение
// сессии, смена пароля, совместимые /login и /register и терминальные ошибки
// OAuth callback.
//
// Незавершённая регистрация через провайдера приходит НЕ через router state:
// `/auth/callback` кладёт ticket в память приложения
// (AuthContext.socialRegistration) и делает replace на `/`. Пока она есть,
// AuthModal открыта в social-режиме (шаг email и/или шаг кода).
const CLOSED = { open: false, tab: 'login', message: '', messageTone: 'info' };

export default function Home() {
  const location = useLocation();
  const {
    loading, isAuthenticated, socialRegistration, clearSocialRegistration,
  } = useAuth();
  const social = socialRegistration ?? null;
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
    // Закрыть модалку посреди регистрации через провайдера — отказаться от
    // неё: ticket в памяти не остаётся, следующий вход начинается заново.
    if (social) clearSocialRegistration();
    // Закрытие сбрасывает сообщение и тон — при следующем открытии их нет.
    setAuth((prev) => ({ ...CLOSED, tab: prev.tab }));
  };
  // Регистрация через провайдера закончилась без аккаунта («Начать заново»
  // либо терминальная ошибка): ticket забыт, модалка остаётся открытой в
  // обычном режиме на нужной вкладке (с сообщением, если оно есть).
  const handleSocialExit = (exit) => {
    clearSocialRegistration();
    setAuth({
      open: true,
      ...authRequestFrom(authEntryState(exit?.tab, exit?.message, exit?.messageTone)),
    });
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
          isOpen={auth.open || social !== null}
          initialTab={auth.tab}
          onClose={handleCloseAuth}
          message={auth.message}
          messageTone={auth.messageTone}
          social={social}
          onSocialExit={handleSocialExit}
        />
      )}
      <CookieBanner />
    </>
  );
}
