import { Link } from 'react-router-dom';
import Button from '../../../components/UI/Button/Button';
import { useMaterial } from '../hooks/useMaterial';
import MaterialArticle from './MaterialArticle';
import styles from './MaterialView.module.css';

/**
 * Чтение материала с состояниями загрузки, недоступности и ошибки.
 * backTo/backLabel — возврат в библиотеку того контекста, откуда открыт материал.
 */
export default function MaterialView({
  uuid,
  backTo,
  backLabel = '← Все материалы',
  fullBleed = false,
}) {
  const { status, item, refetch } = useMaterial(uuid);

  return (
    <>
      <Link to={backTo} className={styles.backLink}>{backLabel}</Link>

      {status === 'loading' && (
        <p className={styles.stateText} role="status">Загружаем материал…</p>
      )}

      {status === 'notFound' && (
        <div className={styles.stateBox} role="status">
          <p className={styles.stateTitle}>Материал недоступен</p>
          <p className={styles.stateHint}>
            Возможно, он снят с публикации или удалён.
          </p>
        </div>
      )}

      {status === 'error' && (
        <div className={styles.stateBox} role="alert">
          <p className={styles.stateTitle}>Не удалось загрузить материал</p>
          <p className={styles.stateHint}>Проверьте соединение и повторите попытку.</p>
          <Button type="button" variant="secondary" size="sm" onClick={refetch}>
            Повторить
          </Button>
        </div>
      )}

      {status === 'ready' && item && <MaterialArticle item={item} fullBleed={fullBleed} />}
    </>
  );
}
