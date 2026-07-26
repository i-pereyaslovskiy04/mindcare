import { useState } from 'react';
import Button from '../../../../components/UI/Button/Button';
import Badge from '../../../../components/UI/Badge/Badge';
import Modal from '../../../../components/Modal/Modal';
import { useAllowedDomains } from '../hooks/useAllowedDomains';
import styles from './EmailDomainsSection.module.css';

/**
 * Управление allowlist почтовых доменов (админ-настройки).
 * Новые аккаунты можно создавать только с доменами из активного списка.
 * Домены не хардкодятся на фронте — всё из /api/admin/email-domains.
 */
export default function EmailDomainsSection() {
  const { items, loading, error, addDomain, setActive } = useAllowedDomains();

  const [domain, setDomain]   = useState('');
  const [comment, setComment] = useState('');
  const [adding, setAdding]   = useState(false);
  const [addError, setAddError] = useState('');

  const [confirm, setConfirm] = useState(null);   // строка домена для отключения
  const [busyId, setBusyId]   = useState(null);
  const [actionError, setActionError] = useState('');

  async function handleAdd(e) {
    e.preventDefault();
    setAddError('');
    if (!domain.trim()) {
      setAddError('Введите домен.');
      return;
    }
    setAdding(true);
    try {
      await addDomain({
        domain: domain.trim(),
        comment: comment.trim() || null,
      });
      setDomain('');
      setComment('');
    } catch (err) {
      setAddError(err.message || 'Не удалось добавить домен.');
    } finally {
      setAdding(false);
    }
  }

  async function handleSetActive(row, isActive) {
    setActionError('');
    setBusyId(row.id);
    try {
      await setActive(row.id, isActive);
      setConfirm(null);
    } catch (err) {
      setActionError(err.message || 'Не удалось изменить домен.');
    } finally {
      setBusyId(null);
    }
  }

  function closeConfirm() {
    setConfirm(null);
    setActionError('');
  }

  return (
    <section className={styles.card}>
      <h2 className={styles.cardTitle}>Разрешённые почтовые домены</h2>
      <p className={styles.cardDesc}>
        Новые аккаунты можно создавать только с адресами из активного списка.
        Существующие пользователи с другими доменами продолжают работать.
      </p>

      <form className={styles.addForm} onSubmit={handleAdd}>
        <div className={styles.addRow}>
          <input
            className={styles.input}
            type="text"
            placeholder="например: donnu.ru"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            disabled={adding}
            aria-label="Домен"
            autoComplete="off"
          />
          <input
            className={styles.input}
            type="text"
            placeholder="Комментарий (необязательно)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            disabled={adding}
            aria-label="Комментарий"
            autoComplete="off"
            maxLength={500}
          />
          <Button type="submit" variant="primary" size="sm" loading={adding}>
            Добавить
          </Button>
        </div>
        {addError && (
          <div className={styles.formError} role="alert">{addError}</div>
        )}
      </form>

      {!confirm && actionError && (
        <div className={styles.formError} role="alert">{actionError}</div>
      )}

      {loading ? (
        <p className={styles.muted}>Загрузка…</p>
      ) : error ? (
        <div className={styles.formError} role="alert">{error}</div>
      ) : items.length === 0 ? (
        <p className={styles.muted}>Список доменов пуст.</p>
      ) : (
        <ul className={styles.list}>
          {items.map((row) => (
            <li key={row.id} className={styles.row}>
              <div className={styles.rowMain}>
                <span className={styles.domain}>{row.domain}</span>
                <Badge tone={row.is_active ? 'success' : 'neutral'}>
                  {row.is_active ? 'активен' : 'отключён'}
                </Badge>
                {row.comment && (
                  <span className={styles.comment}>{row.comment}</span>
                )}
              </div>
              <div className={styles.rowActions}>
                {row.is_active ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    tone="danger"
                    disabled={busyId === row.id}
                    onClick={() => { setActionError(''); setConfirm(row); }}
                  >
                    Отключить
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={busyId === row.id}
                    onClick={() => handleSetActive(row, true)}
                  >
                    Включить
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal
        open={Boolean(confirm)}
        onClose={closeConfirm}
        ariaLabel="Подтверждение отключения домена"
        zIndex={2300}
        size="sm"
      >
        <div className={styles.confirmBody}>
          <h3 className={styles.confirmTitle}>Отключить домен?</h3>
          <p className={styles.confirmText}>
            Новые аккаунты с адресами <strong>@{confirm?.domain}</strong> создавать
            будет нельзя. Существующие пользователи продолжат работать.
          </p>
          {confirm && actionError && (
            <div className={styles.formError} role="alert">{actionError}</div>
          )}
          <div className={styles.confirmActions}>
            <Button
              variant="secondary"
              onClick={closeConfirm}
              disabled={busyId === confirm?.id}
            >
              Отмена
            </Button>
            <Button
              variant="primary"
              tone="danger"
              loading={busyId === confirm?.id}
              onClick={() => handleSetActive(confirm, false)}
            >
              Отключить
            </Button>
          </div>
        </div>
      </Modal>
    </section>
  );
}
