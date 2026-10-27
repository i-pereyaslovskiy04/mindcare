import { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';
import Navbar from '../../components/Navbar/Navbar';
import Hero from './components/Hero';
import QuickActions from './components/QuickActions';
import NewsSection from '../../features/news/components/NewsSection';
import Footer from '../../components/Footer/Footer';
import AuthModal, { REGISTRATION_CONFIRMED_MESSAGE } from '../../features/auth/ui/AuthModal';
import CookieBanner from '../../components/CookieBanner/CookieBanner';
import {
  AUTH_CONFIRM, AUTH_SOCIAL_CONTINUE, authEntryState, authRequestFrom,
  registrationReferenceFrom,
} from '../../features/auth/lib/authEntry';

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

// Шаги модалки, которые задаёт сам маршрут (адрес не меняется и переживает F5):
// /register/confirm#r=<reference> → «Подтверждение регистрации» (ссылка из письма);
// /register/social → продолжение регистрации через Яндекс/VK (ticket в cookie).
const ROUTE_AUTH = new Set([AUTH_CONFIRM, AUTH_SOCIAL_CONTINUE]);

/**
 * routeAuth — шаг AuthModal, заданный маршрутом (`/register/confirm` →
 * 'confirm'). В отличие от одноразового router state он не стирается: адрес
 * вместе с fragment (`#r=<reference>`) остаётся, и перезагрузка снова
 * открывает тот же шаг. Явная ссылка из письма важнее незавершённой
 * регистрации через провайдера: та на этом маршруте не показывается.
 * Уход с адреса ссылки — replace на `/`: закрытие модалки, «Начать
 * регистрацию заново» (вкладка «Регистрация») и успешное подтверждение
 * («Вход» с подставленным email из памяти AuthContext).
 */
export default function Home({ routeAuth = null }) {
  const location = useLocation();
  const {
    loading, isAuthenticated, socialRegistration, clearSocialRegistration,
    resumeSocialRegistration,
    registeredEmail, rememberRegisteredEmail, clearRegisteredEmail,
  } = useAuth();
  const navigate = useNavigate();

  const request = authRequestFrom(location.state);
  const routeTab = ROUTE_AUTH.has(routeAuth) ? routeAuth : null;
  const socialRoute = routeTab === AUTH_SOCIAL_CONTINUE;
  // Ссылка обычной регистрации важнее незавершённой регистрации через провайдера.
  const social = routeTab === AUTH_CONFIRM ? null : (socialRegistration ?? null);
  const registrationReference = routeTab === AUTH_CONFIRM
    ? registrationReferenceFrom(location.hash)
    : null;

  const [auth, setAuth] = useState(() => {
    if (request) return { open: true, ...request };
    // /register/social: модалку открывает сам поток регистрации (social).
    if (socialRoute) return CLOSED;
    if (routeTab) return { ...CLOSED, open: true, tab: routeTab };
    // Регистрация только что подтверждена по ссылке: вход с этим email.
    if (registeredEmail) {
      return {
        open: true, tab: 'login', message: REGISTRATION_CONFIRMED_MESSAGE,
        messageTone: 'info', email: registeredEmail,
      };
    }
    return CLOSED;
  });

  // /register/social: продолжение регистрации через провайдера из письма.
  // Ticket — в HttpOnly cookie; шаг восстанавливает поток (resume) без отправки
  // кода. Один запуск на монтирование (F5 — новое монтирование, снова resume).
  const resumeStarted = useRef(false);
  useEffect(() => {
    if (!socialRoute || loading || isAuthenticated || resumeStarted.current) return;
    resumeStarted.current = true;
    resumeSocialRegistration();
  }, [socialRoute, loading, isAuthenticated, resumeSocialRegistration]);

  // Email передан один раз: после применения на главной он не нужен.
  useEffect(() => {
    if (registeredEmail && !routeTab) clearRegisteredEmail();
  }, [registeredEmail, routeTab, clearRegisteredEmail]);

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
  // Fragment сохраняется: на /register/confirm в нём reference из ссылки.
  const hasRequest = request !== null;
  useEffect(() => {
    if (!hasRequest) return;
    navigate(
      `${location.pathname}${location.search}${location.hash ?? ''}`,
      { replace: true, state: null },
    );
  }, [hasRequest, location.key, location.pathname, location.search, location.hash, navigate]);

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
    // Шаг, заданный маршрутом, закрыт — адрес больше не должен его открывать.
    if (routeTab) navigate('/', { replace: true });
  };
  // Регистрация через провайдера закончилась без аккаунта («Начать заново»
  // либо терминальная ошибка): ticket забыт, модалка остаётся открытой в
  // обычном режиме на нужной вкладке (с сообщением, если оно есть).
  const handleSocialExit = (exit) => {
    clearSocialRegistration();
    const entry = authEntryState(exit?.tab, exit?.message, exit?.messageTone);
    // С адреса продолжения из письма — на главную (вход с сообщением или
    // «Регистрация»): /register/social без регистрации ничего не показывает.
    if (socialRoute) {
      navigate('/', { replace: true, state: entry });
      return;
    }
    setAuth({ open: true, ...authRequestFrom(entry) });
  };
  // Ссылка из письма: регистрация подтверждена — адрес ссылки больше не нужен,
  // на главной откроется вход с этим email (передача только через память).
  const handleRegistrationConfirmed = (email) => {
    rememberRegisteredEmail(email);
    navigate('/', { replace: true });
  };
  // «Начать регистрацию заново»: обычная форма регистрации на главной.
  const handleRegistrationRestart = () => {
    navigate('/', { replace: true, state: authEntryState('register') });
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
          registrationReference={registrationReference}
          onRegistrationConfirmed={routeTab ? handleRegistrationConfirmed : undefined}
          onRegistrationRestart={routeTab ? handleRegistrationRestart : undefined}
          loginEmail={auth.email ?? ''}
        />
      )}
      <CookieBanner />
    </>
  );
}
