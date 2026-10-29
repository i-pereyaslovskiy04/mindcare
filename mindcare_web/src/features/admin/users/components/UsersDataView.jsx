import ResponsiveTable from '../../../../components/UI/ResponsiveTable/ResponsiveTable';
import {
  RoleBadges, StatusBadge, UserActivity, UserMoreActions, UserName, UserPrimaryAction, formatDate,
} from './UserCells';

/**
 * /admin/users на shared ResponsiveTable: здесь только содержимое (что
 * показать), раскладка wide / compact / mobile — в ResponsiveTable. Все
 * режимы получают одни items и один actionContext (обработчики страницы);
 * диалоги монтирует UsersPage.
 */
export default function UsersDataView({ items, loading, error, actionContext }) {
  return (
    <ResponsiveTable
      label="Пользователи"
      items={items}
      getKey={(item) => item.uuid}
      loading={loading}
      error={error ? `Ошибка загрузки: ${error}` : null}
      emptyText="Пользователи не найдены"
      isMuted={(item) => Boolean(item.deleted_at)}
      identity={{
        header: 'Пользователь',
        primary: (item) => <UserName item={item} />,
        secondary: (item) => item.email,
      }}
      status={{
        header: 'Роли и статус',
        width: '16rem',
        render: (item) => (
          <>
            <RoleBadges item={item} />
            <StatusBadge item={item} />
          </>
        ),
      }}
      columns={[
        { key: 'activity', header: 'Активность', render: (item) => <UserActivity item={item} /> },
      ]}
      meta={(item) => [
        { label: 'Регистрация', value: formatDate(item.created_at) },
        { label: 'Последний вход', value: formatDate(item.last_login) },
      ]}
      actions={{
        primary: (item) => <UserPrimaryAction item={item} actionContext={actionContext} />,
        menu: (item) => <UserMoreActions item={item} actionContext={actionContext} />,
      }}
    />
  );
}
