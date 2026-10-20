import { useEffect, useState } from 'react';
import Button from '../../../components/UI/Button/Button';
import { getUnregisteredStudentCards } from '../../../api/supervisor.api';
import UnregisteredCardModal from './UnregisteredCardModal';
import styles from './UnregisteredCardPicker.module.css';

function cardContact(card) {
  return [card.phone, card.email].filter(Boolean).join(' · ');
}

/**
 * Поиск и выбор карточки незарегистрированного студента + создание новой через
 * модалку. onSelect(card, { justCreated }) сообщает родителю выбранную карточку.
 */
export default function UnregisteredCardPicker({ selectedCardId, onSelect }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);

  // Debounced search (q пустой → последние карточки).
  useEffect(() => {
    let cancelled = false;
    const handle = setTimeout(() => {
      setLoading(true);
      setError(null);
      getUnregisteredStudentCards({ q: q.trim() || undefined, size: 20 })
        .then((data) => {
          if (!cancelled) setResults(data.items || []);
        })
        .catch((e) => {
          if (!cancelled) {
            setResults([]);
            setError(e.message || 'Не удалось загрузить карточки');
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [q]);

  function handleCreated(card) {
    setModalOpen(false);
    onSelect(card, { justCreated: true });
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.searchRow}>
        <input
          className={styles.search}
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Поиск по ФИО, email или телефону"
          aria-label="Поиск карточек"
        />
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setModalOpen(true)}
        >
          + Создать карточку
        </Button>
      </div>

      {loading && <span className={styles.hint}>Загрузка карточек…</span>}
      {!loading && error && <span className={styles.err}>{error}</span>}
      {!loading && !error && results.length === 0 && (
        <span className={styles.hint}>
          Карточки не найдены. Создайте новую карточку.
        </span>
      )}

      {!loading && !error && results.length > 0 && (
        <ul className={styles.list}>
          {results.map((card) => {
            const selected = Number(card.id) === Number(selectedCardId);
            const contact = cardContact(card);
            return (
              <li
                key={card.id}
                className={selected ? `${styles.item} ${styles.itemSelected}` : styles.item}
              >
                <div className={styles.itemInfo}>
                  <span className={styles.itemName}>{card.full_name}</span>
                  {contact && <span className={styles.itemContact}>{contact}</span>}
                </div>
                <Button
                  variant={selected ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={() => onSelect(card, {})}
                >
                  {selected ? 'Выбрана' : 'Выбрать'}
                </Button>
              </li>
            );
          })}
        </ul>
      )}

      <UnregisteredCardModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={handleCreated}
      />
    </div>
  );
}
