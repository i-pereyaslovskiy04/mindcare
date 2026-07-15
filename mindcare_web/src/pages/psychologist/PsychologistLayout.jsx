import { useMemo } from 'react';
import CabinetLayout from '../../components/CabinetLayout/CabinetLayout';
import { useMessagesBadge } from '../../features/chat/hooks/useMessagesBadge';

function buildNavSections(messagesBadge) {
  return [
    {
      label: 'Работа',
      items: [
        { key: 'home',      label: 'Главная',      icon: 'home',     to: '/psychologist',           end: true,  disabled: false },
        { key: 'students',  label: 'Мои студенты', icon: 'users',    to: '/psychologist/students',  end: false, disabled: false },
        { key: 'sessions',  label: 'Сессии',       icon: 'calendar', to: '/psychologist/appointments',          disabled: false },
        { key: 'chat',      label: 'Сообщения',    icon: 'chat',     to: '/psychologist/chat',      end: true,  disabled: false,
          badge: messagesBadge > 0 ? String(messagesBadge) : undefined },
        { key: 'materials', label: 'Материалы',    icon: 'articles', to: '/psychologist/materials',             disabled: true  },
      ],
    },
    {
      label: 'Аккаунт',
      items: [
        { key: 'settings',  label: 'Настройки',    icon: 'settings', to: '/psychologist/settings',             disabled: false },
      ],
    },
  ];
}

const CRUMB_LABELS = {
  '/psychologist':               'Главная',
  '/psychologist/students':      'Мои студенты',
  '/psychologist/appointments':  'Сессии',
  '/psychologist/chat':          'Сообщения',
  '/psychologist/settings':      'Настройки',
};

const DYNAMIC_CRUMBS = [
  { prefix: '/psychologist/students/', label: 'Карточка студента' },
];

export default function PsychologistLayout() {
  const messagesBadge = useMessagesBadge('psychologist');
  const navSections = useMemo(() => buildNavSections(messagesBadge), [messagesBadge]);
  return <CabinetLayout cabinetRole="psychologist" navSections={navSections} crumbLabels={CRUMB_LABELS} dynamicCrumbs={DYNAMIC_CRUMBS} />;
}
