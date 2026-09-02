import { useCallback, useEffect, useState } from 'react';
import Icon from '../../components/Icon/Icon';
import Badge from '../../components/UI/Badge/Badge';
import Button from '../../components/UI/Button/Button';
import Checkbox from '../../components/UI/Checkbox/Checkbox';
import ImageUpload from '../../components/UI/ImageUpload/ImageUpload';
import Modal from '../../components/Modal/Modal';
import { ROLE_LABELS } from '../../shared/lib/roles';
import {
  getSupervisorServiceCards,
  createServiceCard,
  updateServiceCard,
  deleteServiceCard,
} from '../../api/serviceCards.api';
import styles from './ServiceCardsPage.module.css';

function useAdminServiceCards() {
  const [items, setItems]     = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getSupervisorServiceCards();
      setItems(data.items || data || []);
    } catch (e) {
      setError(e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);
  return { items, loading, error, refetch: fetch };
}

const EMPTY_FORM = {
  title: '',
  description: '',
  benefitsText: '',
  image: null,
  link_url: '',
  display_order: 0,
  is_active: true,
};

const COLS = 5;

export default function ServiceCardsPage({ cabinetRole = 'supervisor' }) {
  const { items, loading, error, refetch } = useAdminServiceCards();
  const [modal, setModal]   = useState(null); // null | 'create' | item
  const [form, setForm]     = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting]         = useState(false);
  const [deleteError, setDeleteError]   = useState('');

  // Лейбл — из роли МАРШРУТА (cabinetRole), а не legacy user.role.
  const roleLabel = ROLE_LABELS[cabinetRole] ?? '';

  function openCreate() {
    setForm(EMPTY_FORM);
    setSaveErr(null);
    setModal('create');
  }

  function openEdit(item) {
    setForm({
      title:         item.title,
      description:   item.description || '',
      benefitsText:  (item.benefits || []).join('\n'),
      image:         item.image_url ? { uuid: item.image_uuid, url: item.image_url } : null,
      link_url:      item.link_url || '',
      display_order: item.display_order,
      is_active:     item.is_active,
    });
    setSaveErr(null);
    setModal(item);
  }

  function closeModal() { setModal(null); }

  function handleChange(field, value) {
    setForm(f => ({ ...f, [field]: value }));
  }

  function toPayload(f) {
    return {
      title:         f.title.trim(),
      description:   f.description.trim(),
      benefits:      f.benefitsText.split('\n').map(s => s.trim()).filter(Boolean),
      image_uuid:    f.image?.uuid || null,
      link_url:      f.link_url.trim() || null,
      display_order: Number(f.display_order) || 0,
      is_active:     f.is_active,
    };
  }

  async function handleSave() {
    setSaving(true);
    setSaveErr(null);
    try {
      if (modal === 'create') {
        await createServiceCard(toPayload(form));
      } else {
        await updateServiceCard(modal.id, toPayload(form));
      }
      closeModal();
      refetch();
    } catch (e) {
      setSaveErr(e.message || 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(item) {
    try {
      await updateServiceCard(item.id, { is_active: !item.is_active });
      refetch();
    } catch { /* ignore */ }
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteServiceCard(deleteTarget.id);
      setDeleteTarget(null);
      refetch();
    } catch (e) {
      setDeleteError(e.message || 'Ошибка удаления');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.labelTag}>{roleLabel}</div>
          <h1 className={styles.pageTitle}>Карточки <em>услуг</em></h1>
          <p className={styles.pageSub}>Карточки услуг на странице «Услуги».</p>
        </div>
        <Button type="button" variant="primary" onClick={openCreate}>
          <Icon name="plus" size={14} /> Добавить
        </Button>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.thCenter}>Порядок</th>
              <th aria-label="Картинка" />
              <th>Заголовок</th>
              <th>Статус</th>
              <th aria-label="Действия" />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={COLS} className={styles.empty}>Загрузка…</td></tr>
            )}

            {!loading && error && (
              <tr>
                <td colSpan={COLS} className={styles.errorCell}>
                  Ошибка загрузки: {error}{' '}
                  <Button variant="secondary" size="sm" onClick={refetch}>
                    Повторить
                  </Button>
                </td>
              </tr>
            )}

            {!loading && !error && items.length === 0 && (
              <tr>
                <td colSpan={COLS} className={styles.empty}>
                  Нет карточек. На странице «Услуги» показывается стандартный набор.
                </td>
              </tr>
            )}

            {!loading && !error && items.map(item => (
              <tr key={item.id} className={styles.row}>
                <td className={styles.count}>{item.display_order}</td>
                <td>
                  {item.image_url
                    ? <img src={item.image_url} alt="" className={styles.thumb} />
                    : <span className={styles.thumbEmpty}><Icon name="image" size={16} /></span>}
                </td>
                <td>
                  <span className={styles.name}>{item.title}</span>
                </td>
                <td>
                  <Badge tone={item.is_active ? 'success' : 'neutral'}>
                    {item.is_active ? 'Активна' : 'Отключена'}
                  </Badge>
                </td>
                <td className={styles.actionsCell}>
                  <div className={styles.actions}>
                    <Button
                      variant="icon"
                      size="sm"
                      onClick={() => openEdit(item)}
                      aria-label={`Изменить карточку «${item.title}»`}
                      title="Изменить"
                    >
                      <Icon name="edit" size={15} />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => toggleActive(item)}
                    >
                      {item.is_active ? 'Отключить' : 'Включить'}
                    </Button>
                    <Button
                      variant="icon"
                      size="sm"
                      tone="danger"
                      onClick={() => { setDeleteTarget(item); setDeleteError(''); }}
                      aria-label={`Удалить карточку «${item.title}»`}
                      title="Удалить"
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

      <Modal
        open={!!modal}
        onClose={closeModal}
        ariaLabel={modal === 'create' ? 'Новая карточка' : 'Редактировать карточку'}
        size="md"
      >
        <div className={styles.modalBody}>
          <h2 className={styles.modalTitle}>
            {modal === 'create' ? 'Новая карточка' : 'Редактировать карточку'}
          </h2>

          <div className={styles.formField}>
            <label className={styles.formLabel}>Заголовок</label>
            <input
              className={styles.formInput}
              type="text"
              value={form.title}
              onChange={e => handleChange('title', e.target.value)}
              placeholder="Психологическое консультирование"
            />
          </div>

          <div className={styles.formField}>
            <label className={styles.formLabel}>Описание</label>
            <textarea
              className={styles.formTextarea}
              value={form.description}
              onChange={e => handleChange('description', e.target.value)}
              placeholder="Краткое описание услуги."
              rows={3}
            />
          </div>

          <div className={styles.formField}>
            <label className={styles.formLabel}>
              Преимущества <span className={styles.formHint}>— по одному пункту на строку</span>
            </label>
            <textarea
              className={styles.formTextarea}
              value={form.benefitsText}
              onChange={e => handleChange('benefitsText', e.target.value)}
              placeholder={'Разобраться в своей ситуации\nВыявить причины проблемы'}
              rows={4}
            />
          </div>

          <ImageUpload
            value={form.image}
            onChange={val => handleChange('image', val)}
            label="Изображение карточки (необязательно)"
          />

          <div className={styles.formField}>
            <label className={styles.formLabel}>Ссылка кнопки «Записаться» (необязательно)</label>
            <input
              className={styles.formInput}
              type="text"
              value={form.link_url}
              onChange={e => handleChange('link_url', e.target.value)}
              placeholder="/appointments или https://..."
            />
          </div>

          <div className={styles.formField}>
            <label className={styles.formLabel}>Порядок отображения</label>
            <input
              className={styles.formInput}
              type="number"
              min={0}
              value={form.display_order}
              onChange={e => handleChange('display_order', e.target.value)}
            />
          </div>

          <div className={styles.checkboxGroup}>
            <Checkbox
              checked={form.is_active}
              onChange={v => handleChange('is_active', v)}
              label="Активна"
            />
          </div>

          {saveErr && <div className={styles.saveErr}>{saveErr}</div>}

          <div className={styles.modalActions}>
            <Button type="button" variant="secondary" onClick={closeModal}>Отмена</Button>
            <Button
              type="button"
              variant="primary"
              disabled={saving || !form.title.trim() || !form.description.trim()}
              onClick={handleSave}
            >
              {saving ? 'Сохраняем…' : 'Сохранить'}
            </Button>
          </div>
        </div>
      </Modal>

      {deleteTarget && (
        <div className={styles.overlay} onClick={() => !deleting && setDeleteTarget(null)}>
          <div className={styles.dialog} onClick={e => e.stopPropagation()}>
            <h3 className={styles.dialogTitle}>Удалить карточку?</h3>
            <p className={styles.dialogBody}>«{deleteTarget.title}» будет удалена безвозвратно. Действие необратимо.</p>
            {deleteError && <p className={styles.dialogError}>{deleteError}</p>}
            <div className={styles.dialogActions}>
              <Button variant="secondary" onClick={() => setDeleteTarget(null)} disabled={deleting}>
                Отмена
              </Button>
              <Button variant="danger" onClick={handleDeleteConfirm} disabled={deleting}>
                {deleting ? 'Удаление…' : 'Удалить'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
