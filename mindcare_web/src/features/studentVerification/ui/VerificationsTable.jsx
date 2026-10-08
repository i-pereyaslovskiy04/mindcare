import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import {
  formatVerificationDate,
  verificationStatusLabel,
  verificationStatusTone,
} from '../lib/status';
import styles from './VerificationsTable.module.css';

/**
 * Список заявок подтверждения студента для supervisor (ADR-029).
 * Номер билета в списке отсутствует (backend его не отдаёт) — только в карточке.
 */
export default function VerificationsTable({ items, onOpen }) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Пользователь</th>
            <th scope="col">Факультет</th>
            <th scope="col">Подана</th>
            <th scope="col">Статус</th>
            <th scope="col">Проверил</th>
            <th scope="col"><span className={styles.srOnly}>Действия</span></th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.uuid}>
              <td>
                <div className={styles.name}>{item.student?.full_name || '—'}</div>
                <div className={styles.email}>{item.student?.email}</div>
                {item.student && item.student.is_active === false && (
                  <Badge tone="error" className={styles.inlineBadge}>Аккаунт отключён</Badge>
                )}
              </td>
              <td>{item.faculty?.label || '—'}</td>
              <td className={styles.nowrap}>{formatVerificationDate(item.submitted_at)}</td>
              <td>
                <Badge tone={verificationStatusTone(item.status)}>
                  {verificationStatusLabel(item.status)}
                </Badge>
              </td>
              <td>
                {item.reviewer?.full_name ? (
                  <>
                    <div>{item.reviewer.full_name}</div>
                    <div className={styles.email}>{formatVerificationDate(item.reviewed_at)}</div>
                  </>
                ) : (
                  <span className={styles.muted}>—</span>
                )}
              </td>
              <td className={styles.actions}>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => onOpen(item.uuid)}
                  aria-label={`Открыть заявку: ${item.student?.full_name || 'пользователь'}`}
                >
                  Открыть
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
