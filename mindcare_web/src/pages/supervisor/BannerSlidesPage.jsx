import { useCallback, useEffect, useState } from 'react';
import Icon from '../../components/Icon/Icon';
import Badge from '../../components/UI/Badge/Badge';
import Button from '../../components/UI/Button/Button';
import Checkbox from '../../components/UI/Checkbox/Checkbox';
import ImageUpload from '../../components/UI/ImageUpload/ImageUpload';
import Select from '../../components/UI/Select/Select';
import Modal from '../../components/Modal/Modal';
import { ROLE_LABELS } from '../../shared/lib/roles';
import {
  getSupervisorBannerSlides,
  createBannerSlide,
  updateBannerSlide,
  deleteBannerSlide,
} from '../../api/bannerSlides.api';
import styles from './BannerSlidesPage.module.css';

// Известные страницы-получатели — расширяется вместе с
// app/banner_slides/schemas.py::BannerPlacement на бэкенде.
const PLACEMENT_OPTIONS = [
  { value: 'home', label: 'Главная' },
  { value: 'services', label: 'Услуги' },
];
const PLACEMENT_LABELS = Object.fromEntries(
  PLACEMENT_OPTIONS.map(o => [o.value, o.label])
);
const PLACEMENT_FILTER_OPTIONS = [
  { value: '', label: 'Все страницы' },
  ...PLACEMENT_OPTIONS,
];
const PLACEMENT_ORDER = Object.fromEntries(
  PLACEMENT_OPTIONS.map((o, i) => [o.value, i])
);

// Список сортируется по принадлежности к странице (порядок PLACEMENT_OPTIONS),
// внутри страницы — по display_order, как показывает сам слайдер.
function byPlacement(a, b) {
  const pa = PLACEMENT_ORDER[a.placement] ?? PLACEMENT_OPTIONS.length;
  const pb = PLACEMENT_ORDER[b.placement] ?? PLACEMENT_OPTIONS.length;
  if (pa !== pb) return pa - pb;
  return a.display_order - b.display_order;
}

function useBannerSlides(placement) {
  const [items, setItems]     = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getSupervisorBannerSlides(placement || undefined);
      setItems(data.items || data || []);
    } catch (e) {
      setError(e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, [placement]);

  useEffect(() => { fetch(); }, [fetch]);
  return { items, loading, error, refetch: fetch };
}

const EMPTY_FORM = {
  label: '',
  title: '',
  highlight: '',
  sub: '',
  image: null,
  link_url: '',
  placement: 'home',
  display_order: 0,
  is_active: true,
};

const COLS = 6;

export default function BannerSlidesPage({ cabinetRole = 'supervisor' }) {
  const [placementFilter, setPlacementFilter] = useState('');
  const { items: fetchedItems, loading, error, refetch } = useBannerSlides(placementFilter);
  const items = [...fetchedItems].sort(byPlacement);
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
      label:         item.label || '',
      title:         item.title,
      highlight:     item.highlight || '',
      sub:           item.sub || '',
      image:         item.image_url ? { uuid: item.image_uuid, url: item.image_url } : null,
      link_url:      item.link_url || '',
      placement:     item.placement,
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
      label:         f.label.trim() || null,
      title:         f.title.trim(),
      highlight:     f.highlight.trim() || null,
      sub:           f.sub.trim() || null,
      image_uuid:    f.image?.uuid || null,
      link_url:      f.link_url.trim() || null,
      placement:     f.placement,
      display_order: Number(f.display_order) || 0,
      is_active:     f.is_active,
    };
  }

  async function handleSave() {
    setSaving(true);
    setSaveErr(null);
    try {
      if (modal === 'create') {
        await createBannerSlide(toPayload(form));
      } else {
        await updateBannerSlide(modal.id, toPayload(form));
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
      await updateBannerSlide(item.id, { is_active: !item.is_active });
      refetch();
    } catch { /* ignore */ }
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteBannerSlide(deleteTarget.id);
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
          <h1 className={styles.pageTitle}>Баннер <em>сайта</em></h1>
          <p className={styles.pageSub}>Слайды баннера — главная страница и страницы услуг.</p>
        </div>
        <Button type="button" variant="primary" onClick={openCreate}>
          <Icon name="plus" size={14} /> Добавить
        </Button>
      </div>

      <div className={styles.toolbar}>
        <Select
          value={placementFilter}
          options={PLACEMENT_FILTER_OPTIONS}
          onChange={setPlacementFilter}
          placeholder="Все страницы"
        />
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.thCenter}>Порядок</th>
              <th aria-label="Картинка" />
              <th>Заголовок</th>
              <th>Страница</th>
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
                  Нет слайдов. На соответствующей странице показывается стандартный баннер.
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
                  {item.highlight && <span className={styles.nameSub}>{item.highlight}</span>}
                </td>
                <td>
                  <Badge tone="neutral">{PLACEMENT_LABELS[item.placement] || item.placement}</Badge>
                </td>
                <td>
                  <Badge tone={item.is_active ? 'success' : 'neutral'}>
                    {item.is_active ? 'Активен' : 'Отключён'}
                  </Badge>
                </td>
                <td className={styles.actionsCell}>
                  <div className={styles.actions}>
                    <Button
                      variant="icon"
                      size="sm"
                      onClick={() => openEdit(item)}
                      aria-label={`Изменить слайд «${item.title}»`}
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
                      aria-label={`Удалить слайд «${item.title}»`}
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
        ariaLabel={modal === 'create' ? 'Новый слайд' : 'Редактировать слайд'}
        size="md"
      >
        <div className={styles.modalBody}>
          <h2 className={styles.modalTitle}>
            {modal === 'create' ? 'Новый слайд' : 'Редактировать слайд'}
          </h2>

          <div className={styles.formField}>
            <label className={styles.formLabel}>Страница</label>
            <Select
              value={form.placement}
              options={PLACEMENT_OPTIONS}
              onChange={val => handleChange('placement', val)}
            />
          </div>

          <div className={styles.formField}>
            <label className={styles.formLabel}>Метка (необязательно)</label>
            <input
              className={styles.formInput}
              type="text"
              value={form.label}
              onChange={e => handleChange('label', e.target.value)}
              placeholder="Психологическая служба · ДонГУ"
            />
          </div>

          <div className={styles.formField}>
            <label className={styles.formLabel}>Заголовок</label>
            <input
              className={styles.formInput}
              type="text"
              value={form.title}
              onChange={e => handleChange('title', e.target.value)}
              placeholder="Забота о вашей"
            />
          </div>

          <div className={styles.formField}>
            <label className={styles.formLabel}>Акцент (необязательно)</label>
            <input
              className={styles.formInput}
              type="text"
              value={form.highlight}
              onChange={e => handleChange('highlight', e.target.value)}
              placeholder="душевной гармонии"
            />
          </div>

          <div className={styles.formField}>
            <label className={styles.formLabel}>Подзаголовок (необязательно)</label>
            <textarea
              className={styles.formTextarea}
              value={form.sub}
              onChange={e => handleChange('sub', e.target.value)}
              placeholder="Короткое описание в одну-две строки."
              rows={3}
            />
          </div>

          <ImageUpload
            value={form.image}
            onChange={val => handleChange('image', val)}
            label="Изображение слайда (необязательно)"
          />

          <div className={styles.formField}>
            <label className={styles.formLabel}>Ссылка кнопки (необязательно)</label>
            <input
              className={styles.formInput}
              type="text"
              value={form.link_url}
              onChange={e => handleChange('link_url', e.target.value)}
              placeholder="/services или https://..."
            />
          </div>

          <div className={styles.formRow}>
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
          </div>

          <div className={styles.checkboxGroup}>
            <Checkbox
              checked={form.is_active}
              onChange={v => handleChange('is_active', v)}
              label="Активен"
            />
          </div>

          {saveErr && <div className={styles.saveErr}>{saveErr}</div>}

          <div className={styles.modalActions}>
            <Button type="button" variant="secondary" onClick={closeModal}>Отмена</Button>
            <Button
              type="button"
              variant="primary"
              disabled={saving || !form.title.trim()}
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
            <h3 className={styles.dialogTitle}>Удалить слайд?</h3>
            <p className={styles.dialogBody}>«{deleteTarget.title}» будет удалён безвозвратно. Действие необратимо.</p>
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
