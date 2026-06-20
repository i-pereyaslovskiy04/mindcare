import Icon from '../../../../components/Icon/Icon';
import Button from '../../../../components/UI/Button/Button';
import Badge from '../../../../components/UI/Badge/Badge';
import Tag from '../../../../components/UI/Tag/Tag';
import styles from './TestsTable.module.css';

const SKELETON_ROWS = 6;
const SCORING_LABEL = { sum: 'Сумма баллов', average: 'Среднее' };

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU');
}

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: 6 }, (_, i) => (
        <td key={i}><span className={styles.skeletonCell} /></td>
      ))}
    </tr>
  );
}

export default function TestsTable({ items, loading, error, onEdit, onDelete }) {
  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Название</th>
            <th>Вопросов</th>
            <th>Подсчёт</th>
            <th>Статус</th>
            <th>Создан</th>
            <th aria-label="Действия" />
          </tr>
        </thead>
        <tbody>
          {loading && Array.from({ length: SKELETON_ROWS }, (_, i) => <SkeletonRow key={i} />)}

          {!loading && error && (
            <tr>
              <td colSpan={6} className={styles.stateCell}>
                <span className={styles.errorText}>Ошибка загрузки: {error}</span>
              </td>
            </tr>
          )}

          {!loading && !error && items.length === 0 && (
            <tr>
              <td colSpan={6} className={styles.stateCell}>Тестов пока нет</td>
            </tr>
          )}

          {!loading && !error && items.map((item) => (
            <tr key={item.uuid} className={styles.row}>
              <td>
                <span className={styles.title}>{item.title}</span>
                {item.categories?.length > 0 && (
                  <div className={styles.tags}>
                    {item.categories.map((c) => (
                      <Tag key={c.id} variant="category">{c.name}</Tag>
                    ))}
                  </div>
                )}
                {item.created_by_name && (
                  <span className={styles.meta}>{item.created_by_name}</span>
                )}
              </td>
              <td className={styles.num}>{item.question_count}</td>
              <td className={styles.scoring}>{SCORING_LABEL[item.scoring] || item.scoring}</td>
              <td>
                <Badge tone={item.is_active ? 'success' : 'warning'}>
                  {item.is_active ? 'Активен' : 'Скрыт'}
                </Badge>
              </td>
              <td className={styles.date}>{formatDate(item.created_at)}</td>
              <td className={styles.actionsCell}>
                <div className={styles.actions}>
                  <Button
                    variant="icon"
                    size="sm"
                    onClick={() => onEdit(item)}
                    aria-label={`Редактировать «${item.title}»`}
                  >
                    <Icon name="edit" size={15} />
                  </Button>
                  <Button
                    variant="icon"
                    size="sm"
                    tone="danger"
                    onClick={() => onDelete(item)}
                    aria-label={`Удалить «${item.title}»`}
                  >
                    <Icon name="trash" size={15} />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
