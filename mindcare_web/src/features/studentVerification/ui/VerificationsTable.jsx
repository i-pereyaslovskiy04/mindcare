import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import ResponsiveTable from '../../../components/UI/ResponsiveTable/ResponsiveTable';
import { formatVerificationDateTime } from '../lib/status';
import styles from './VerificationsTable.module.css';

/**
 * Очередь заявок подтверждения студента для supervisor (ADR-029) на shared
 * ResponsiveTable: здесь только содержимое, раскладку wide / compact /
 * mobile задаёт ResponsiveTable. Только ожидающие проверки, поэтому статуса
 * заявки и проверившего нет. Номер билета в списке отсутствует (backend его
 * не отдаёт) — только в карточке, которая читается при открытии (журнал).
 * Состояния очереди (pageLoading, ошибка, пусто) показывает страница.
 * Действие одно — «Открыть», меню «⋮» не нужно.
 */
export default function VerificationsTable({ items, onOpen }) {
  return (
    <ResponsiveTable
      label="Заявки на подтверждение статуса студента"
      items={items}
      getKey={(item) => item.uuid}
      identity={{
        header: 'Пользователь',
        primary: (item) => item.student?.full_name || '—',
        secondary: (item) => (
          <>
            {item.student?.email}
            {item.student && item.student.is_active === false && (
              <span className={styles.flag}>
                <Badge tone="error">Аккаунт отключён</Badge>
              </span>
            )}
          </>
        ),
      }}
      status={{
        header: 'Факультет',
        render: (item) => <span className={styles.faculty}>{item.faculty?.label || '—'}</span>,
      }}
      columns={[
        {
          key: 'submitted',
          header: 'Подана',
          render: (item) => (
            <span className={styles.nowrap}>{formatVerificationDateTime(item.submitted_at)}</span>
          ),
        },
      ]}
      meta={(item) => [
        { label: 'Подана', value: formatVerificationDateTime(item.submitted_at) },
      ]}
      actions={{
        primary: (item) => (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onOpen(item.uuid)}
            aria-label={`Открыть заявку: ${item.student?.full_name || 'пользователь'}`}
          >
            Открыть
          </Button>
        ),
      }}
    />
  );
}
