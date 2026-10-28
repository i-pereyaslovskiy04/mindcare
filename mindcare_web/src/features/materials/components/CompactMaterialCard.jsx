import { Link } from 'react-router-dom';
import Icon from '../../../components/Icon/Icon';
import styles from './CompactMaterialCard.module.css';

/**
 * Компактная карточка материала для кабинетов (прежний вид студенческой
 * библиотеки): плашка 130 px с обложкой или значком, тип материала, заголовок,
 * дата и тема. Вся карточка кликабельна через ссылку заголовка (растянутая
 * область), кнопка «Избранное» — отдельный элемент поверх, не вложенный в ссылку.
 *
 * favorite: undefined — кнопки нет; true/false — состояние; onToggleFavorite(item).
 */
export default function CompactMaterialCard({
  item, to, favorite, onToggleFavorite, favoritePending = false,
}) {
  const href = to || `/materials/${item.id}`;
  const showFavorite = typeof favorite === 'boolean' && typeof onToggleFavorite === 'function';

  return (
    <article className={styles.card}>
      <div className={styles.img}>
        {item.image
          ? <img src={item.image} alt="" className={styles.cover} loading="lazy" />
          : <Icon name="articles" size={36} />}
        {showFavorite && (
          <button
            type="button"
            className={`${styles.fav} ${favorite ? styles.favOn : ''}`}
            onClick={() => onToggleFavorite(item)}
            disabled={favoritePending}
            aria-pressed={favorite}
            aria-label={favorite
              ? `Убрать «${item.title}» из избранного`
              : `Добавить «${item.title}» в избранное`}
          >
            <Icon name={favorite ? 'heart' : 'heart-o'} size={14} />
          </button>
        )}
      </div>
      <div className={styles.body}>
        {item.category && <span className={styles.topic}>{item.category}</span>}
        <Link to={href} className={styles.title}>{item.title}</Link>
        <div className={styles.meta}>
          {item.date
            ? <time dateTime={item.dateTime || undefined}>{item.date}</time>
            : <span />}
          {item.topics?.[0] && (
            <span>
              <span className="visually-hidden">Тема: </span>
              {item.topics[0]}
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
