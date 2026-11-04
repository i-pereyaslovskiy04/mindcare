import { useState } from 'react';
import Button from '../../../components/UI/Button/Button';
import ConfirmDialog from '../../assignments/ui/ConfirmDialog';
import useCampaignResponses from '../hooks/useCampaignResponses';
import styles from './CampaignResponses.module.css';

const GENDER = { male: 'Муж', female: 'Жен' };

function formatDate(value) {
  try {
    return new Date(value).toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return '';
  }
}

/**
 * Участники кампании: ФИО, факультет, специальность, возраст, пол, время.
 * Удаление ответа — безвозвратно (вместе с записью согласия), с подтверждением.
 * onDeleted — после успешного удаления (обновить счётчик кампании).
 */
export default function CampaignResponses({ campaignUuid, onDeleted }) {
  const list = useCampaignResponses(campaignUuid, true);
  const [pending, setPending] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  async function confirmDelete() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await list.remove(pending.uuid);
      setPending(null);
      onDeleted?.();
    } catch (err) {
      setDeleteError(err?.message || 'Не удалось удалить ответ');
    } finally {
      setDeleting(false);
    }
  }

  if (list.loading) return <p className={styles.muted} role="status">Загрузка участников…</p>;
  if (list.error) return <p className={styles.error} role="alert">{list.error}</p>;
  if (!list.items.length) return <p className={styles.muted}>Пока никто не прошёл тестирование.</p>;

  return (
    <div className={styles.wrap}>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">ФИО</th>
              <th scope="col">Факультет</th>
              <th scope="col">Специальность</th>
              <th scope="col">Возраст</th>
              <th scope="col">Пол</th>
              <th scope="col">Пройдено</th>
              <th scope="col"><span className={styles.srOnly}>Действия</span></th>
            </tr>
          </thead>
          <tbody>
            {list.items.map((r) => (
              <tr key={r.uuid}>
                <td>{r.full_name}</td>
                <td>{r.faculty_label || r.faculty_code}</td>
                <td>{r.specialty}</td>
                <td>{r.age}</td>
                <td>{GENDER[r.gender] || r.gender}</td>
                <td>{formatDate(r.submitted_at)}</td>
                <td>
                  <Button type="button" size="sm" variant="secondary"
                    onClick={() => { setDeleteError(null); setPending(r); }}
                    aria-label={`Удалить ответ: ${r.full_name}`}>
                    Удалить
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {list.hasMore && (
        <Button type="button" variant="secondary" onClick={list.loadMore}
          loading={list.loadingMore}>
          Показать ещё
        </Button>
      )}
      <ConfirmDialog
        open={Boolean(pending)}
        title="Удалить ответ участника?"
        description={pending
          ? `Ответы и анкета «${pending.full_name}» будут удалены безвозвратно вместе с записью согласия.`
          : ''}
        confirmLabel="Удалить"
        confirmTone="danger"
        loading={deleting}
        error={deleteError}
        onConfirm={confirmDelete}
        onClose={() => setPending(null)}
      />
    </div>
  );
}
