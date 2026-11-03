import { useCallback, useEffect, useState } from 'react';
import Icon from '../../components/Icon/Icon';
import Badge from '../../components/UI/Badge/Badge';
import Button from '../../components/UI/Button/Button';
import Checkbox from '../../components/UI/Checkbox/Checkbox';
import ImageUpload from '../../components/UI/ImageUpload/ImageUpload';
import Modal from '../../components/Modal/Modal';
import ResponsiveTable from '../../components/UI/ResponsiveTable/ResponsiveTable';
import ActionsMenu from '../../components/UI/ActionsMenu/ActionsMenu';
import {
  getSupervisorServiceCards,
  createServiceCard,
  updateServiceCard,
  deleteServiceCard,
} from '../../api/serviceCards.api';
import styles from './ServiceCardsPage.module.css';

// Битая ссылка на картинку: вместо значка браузера — плашка media.
function hideBrokenImage(e) {
  e.currentTarget.style.visibility = 'hidden';
}

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


export default function ServiceCardsPage() {
  const { items, loading, error, refetch } = useAdminServiceCards();
  const [modal, setModal]   = useState(null); // null | 'create' | item
  const [form, setForm]     = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting]         = useState(false);
  const [deleteError, setDeleteError]   = useState('');


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
          <h1 className={styles.pageTitle}>Карточки <em>услуг</em></h1>
          <p className={styles.pageSub}>Карточки услуг на странице «Услуги».</p>
        </div>
        <Button type="button" variant="primary" onClick={openCreate}>
          <Icon name="plus" size={14} /> Добавить
        </Button>
      </div>

      {/* Ошибка с «Повторить» — снаружи таблицы, как у Engagements; загрузку,
          пусто и записи показывает shared ResponsiveTable. */}
      {!loading && error ? (
        <div className={styles.stateBox}>
          <div className={styles.errorText}>Ошибка загрузки: {error}</div>
          <Button variant="secondary" size="sm" onClick={refetch}>Повторить</Button>
        </div>
      ) : (
        <ResponsiveTable
          label="Карточки услуг"
          items={items}
          getKey={(item) => item.id}
          loading={loading}
          emptyText="Нет карточек. На странице «Услуги» показывается стандартный набор."
          identity={{
            header: 'Карточка',
            media: (item) => (item.image_url
              ? <img src={item.image_url} alt="" onError={hideBrokenImage} />
              : null),
            primary: (item) => item.title,
          }}
          status={{
            header: 'Статус',
            render: (item) => (
              <Badge tone={item.is_active ? 'success' : 'neutral'}>
                {item.is_active ? 'Активна' : 'Отключена'}
              </Badge>
            ),
          }}
          columns={[
            {
              key: 'order',
              header: 'Порядок',
              render: (item) => <span className={styles.params}>{item.display_order}</span>,
            },
          ]}
          meta={(item) => [{ label: 'Порядок', value: item.display_order }]}
          actions={{
            primary: (item) => (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => openEdit(item)}
                aria-label={`Изменить карточку «${item.title}»`}
              >
                Изменить
              </Button>
            ),
            menu: (item) => (
              <ActionsMenu
                triggerLabel={`Другие действия: карточка «${item.title}»`}
                items={[
                  item.is_active
                    ? { id: 'toggle', label: 'Отключить', onSelect: () => toggleActive(item) }
                    : { id: 'toggle', label: 'Включить', tone: 'success', onSelect: () => toggleActive(item) },
                  { id: 'delete', label: 'Удалить', tone: 'danger',
                    onSelect: () => { setDeleteTarget(item); setDeleteError(''); } },
                ]}
              />
            ),
          }}
        />
      )}

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
              Преимущества <span className={styles.formHint}>- по одному пункту на строку</span>
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
