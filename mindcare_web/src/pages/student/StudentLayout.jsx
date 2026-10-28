import { useMemo } from 'react';
import CabinetLayout from '../../components/CabinetLayout/CabinetLayout';
import { useAuth } from '../../features/auth/AuthContext';
import useActiveAssignmentsCount from '../../features/assignments/hooks/useActiveAssignmentsCount';
import { useMessagesBadge } from '../../features/chat/hooks/useMessagesBadge';
import { normalizeRoles } from '../../shared/lib/roles';

/** Бейдж: число (99+ при большом), доступная подпись — точное число. */
function assignmentsBadge(count) {
  if (!(count > 0)) return {};
  return {
    badge: count > 99 ? '99+' : String(count),
    badgeLabel: `активных заданий: ${count}`,
  };
}

function buildNavSections(messagesBadge, assignmentsCount) {
  return [
    {
      label: 'Самопомощь',
      items: [
        { key: 'home',      label: 'Главная',            icon: 'home',     to: '/student',           end: true },
        { key: 'diary',     label: 'Дневник состояния',  icon: 'diary',    to: '/student/diary',     end: true },
        { key: 'tests',     label: 'Тесты',              icon: 'tests',    to: '/student/tests',     end: false },
        { key: 'materials', label: 'Материалы и статьи', icon: 'articles', to: '/student/materials', end: false },
      ],
    },
    {
      label: 'Терапия',
      items: [
        { key: 'tasks',    label: 'Задания психолога', icon: 'tasks',    to: '/student/tasks',    end: true,
          ...assignmentsBadge(assignmentsCount) },
        { key: 'chat',     label: 'Сообщения',         icon: 'chat',     to: '/student/chat',     end: true,
          badge: messagesBadge > 0 ? String(messagesBadge) : undefined },
        { key: 'calendar',      label: 'Календарь и сессии',  icon: 'calendar', to: '/student/calendar',      end: true },
        { key: 'group-sessions', label: 'Групповые занятия', icon: 'users',    to: '/student/group-sessions', end: true },
      ],
    },
    {
      label: 'Аккаунт',
      items: [
        { key: 'settings', label: 'Настройки', icon: 'settings', to: '/student/settings', end: true },
      ],
    },
  ];
}

const CRUMB_LABELS = {
  '/student':           'Главная',
  '/student/diary':     'Дневник состояния',
  '/student/tests':     'Тесты',
  '/student/materials': 'Материалы и статьи',
  '/student/tasks':     'Задания психолога',
  '/student/chat':      'Сообщения',
  '/student/calendar':       'Календарь и сессии',
  '/student/group-sessions': 'Групповые занятия',
  '/student/settings':  'Настройки',
};

// parent — раздел из CRUMB_LABELS, промежуточная крошка-ссылка.
const DYNAMIC_CRUMBS = [
  { prefix: '/student/materials/', label: 'Материал', parent: '/student/materials' },
];

export default function StudentLayout() {
  const { user, isImpersonating } = useAuth();
  const messagesBadge = useMessagesBadge('student');
  // Задания недоступны в режиме «под именем» (backend отвечает 403): счётчик
  // не запрашивается вне этих условий.
  const canSeeAssignments = !isImpersonating && normalizeRoles(user).includes('student');
  const assignmentsCount = useActiveAssignmentsCount(canSeeAssignments, user?.id ?? null);
  const navSections = useMemo(
    () => buildNavSections(messagesBadge, assignmentsCount),
    [messagesBadge, assignmentsCount],
  );
  return (
    <CabinetLayout
      cabinetRole="student"
      navSections={navSections}
      crumbLabels={CRUMB_LABELS}
      dynamicCrumbs={DYNAMIC_CRUMBS}
    />
  );
}
