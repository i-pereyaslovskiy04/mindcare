import { useMemo } from 'react';
import CabinetLayout from '../../components/CabinetLayout/CabinetLayout';
import { useAuth } from '../../features/auth/AuthContext';
import usePendingVerificationsCount from '../../features/studentVerification/hooks/usePendingVerificationsCount';
import useReviewQueueCounts, { reviewBadge } from '../../features/moderation/hooks/useReviewQueueCounts';
import { normalizeRoles } from '../../shared/lib/roles';

/** Бейдж: число (99+ при большом), доступная подпись — точное число. */
function pendingBadge(count) {
  if (!(count > 0)) return {};
  return {
    badge: count > 99 ? '99+' : String(count),
    badgeLabel: `ожидают проверки: ${count}`,
  };
}

function buildNavSections(pendingCount, reviewCounts) {
  return [
    {
      label: 'Супервизия',
      items: [
        { key: 'home',          label: 'Главная',              icon: 'home',     to: '/supervisor',                    end: true,  disabled: false },
        { key: 'engagements',   label: 'Назначение психологов', icon: 'tasks',   to: '/supervisor/engagements',        end: true,  disabled: false },
        { key: 'meeting-types', label: 'Типы встреч',          icon: 'calendar', to: '/supervisor/meeting-types',      end: true,  disabled: false },
        { key: 'banner-slides', label: 'Баннер',               icon: 'image',    to: '/supervisor/banner-slides',      end: true,  disabled: false },
        { key: 'service-cards', label: 'Карточки услуг',       icon: 'image',    to: '/supervisor/service-cards',      end: true,  disabled: false },
        { key: 'tests',         label: 'Тесты',                icon: 'tests',    to: '/supervisor/tests',                          disabled: false,
          ...reviewBadge(reviewCounts.tests) },
        { key: 'materials',     label: 'Материалы',            icon: 'articles', to: '/supervisor/materials',        end: true,  disabled: false,
          ...reviewBadge(reviewCounts.articles) },
        { key: 'schedule',      label: 'Расписание',           icon: 'calendar', to: '/supervisor/schedule',           end: true,  disabled: false },
        { key: 'booking',       label: 'Запись',               icon: 'calendar', to: '/supervisor/booking',            end: true,  disabled: false },
        { key: 'group-sessions',label: 'Групповые занятия',    icon: 'users',    to: '/supervisor/group-sessions',     end: true,  disabled: false },
        { key: 'student-verifications', label: 'Подтверждение студентов', icon: 'check', to: '/supervisor/student-verifications', end: true, disabled: false,
          ...pendingBadge(pendingCount) },
        { key: 'psych',        label: 'Психологи',            icon: 'users',    to: '/supervisor/psychologists',                  disabled: true  },
        { key: 'reports',       label: 'Отчёты',               icon: 'articles', to: '/supervisor/reports',                        disabled: true  },
      ],
    },
    {
      label: 'Аккаунт',
      items: [
        { key: 'settings', label: 'Настройки', icon: 'settings', to: '/supervisor/settings', disabled: false },
      ],
    },
  ];
}

const CRUMB_LABELS = {
  '/supervisor':                  'Главная',
  '/supervisor/engagements':      'Назначение психологов',
  '/supervisor/meeting-types':    'Типы встреч',
  '/supervisor/banner-slides':    'Баннер',
  '/supervisor/service-cards':    'Карточки услуг',
  '/supervisor/tests':            'Тесты',
  '/supervisor/materials':        'Материалы',
  '/supervisor/schedule':         'Расписание',
  '/supervisor/booking':          'Запись',
  '/supervisor/group-sessions':   'Групповые занятия',
  '/supervisor/student-verifications': 'Подтверждение студентов',
  '/supervisor/settings':         'Настройки',
};

// parent — раздел из CRUMB_LABELS, промежуточная крошка-ссылка.
const DYNAMIC_CRUMBS = [
  { prefix: '/supervisor/tests/', label: 'Тест', parent: '/supervisor/tests' },
];

export default function SupervisorLayout() {
  const { user, isImpersonating } = useAuth();
  // Проверка заявок — только прямой supervisor (backend отвечает 403 в режиме
  // «под именем»): счётчик не запрашивается вне этих условий.
  const canReview = !isImpersonating && normalizeRoles(user).includes('supervisor');
  const pendingCount = usePendingVerificationsCount(canReview, user?.id ?? null);
  // Очереди модерации материалов и тестов (бейджи «Материалы» и «Тесты»).
  const reviewCounts = useReviewQueueCounts(canReview, user?.id ?? null);
  const navSections = useMemo(
    () => buildNavSections(pendingCount, reviewCounts), [pendingCount, reviewCounts],
  );
  return (
    <CabinetLayout
      cabinetRole="supervisor"
      navSections={navSections}
      crumbLabels={CRUMB_LABELS}
      dynamicCrumbs={DYNAMIC_CRUMBS}
    />
  );
}
