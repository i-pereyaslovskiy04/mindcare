import { useCallback, useEffect, useState } from 'react';
import Icon from '../../components/Icon/Icon';
import Badge from '../../components/UI/Badge/Badge';
import Button from '../../components/UI/Button/Button';
import Checkbox from '../../components/UI/Checkbox/Checkbox';
import Modal from '../../components/Modal/Modal';
import ResponsiveTable from '../../components/UI/ResponsiveTable/ResponsiveTable';
import ActionsMenu from '../../components/UI/ActionsMenu/ActionsMenu';
import {
  getMeetingTypes,
  createMeetingType,
  updateMeetingType,
} from '../../api/appointments.api';
import styles from './MeetingTypesPage.module.css';

function useMeetingTypes() {
  const [items, setItems]   = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMeetingTypes();
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
  name: '',
  description: '',
  duration_minutes: 50,
  buffer_minutes: 10,
  allow_in_person: true,
  allow_online: true,
  is_group: false,
  is_active: true,
  is_bookable: true,
  display_order: 0,
};

// Параметры строки: длительность (+ буфер), форматы и вид встречи.
function durationText(item) {
  return item.buffer_minutes > 0
    ? `${item.duration_minutes} мин + ${item.buffer_minutes} мин буфер`
    : `${item.duration_minutes} мин`;
}

function formatText(item) {
  const formats = [item.allow_online && 'онлайн', item.allow_in_person && 'очно'].filter(Boolean);
  const text = formats.join(' и ') || 'формат не задан';
  return text[0].toUpperCase() + text.slice(1);
}

const kindText = (item) => (item.is_group ? 'Групповой' : 'Индивидуальный');

export default function MeetingTypesPage() {
  const { items, loading, error, refetch } = useMeetingTypes();
  const [modal, setModal]   = useState(null); // null | 'create' | item
  const [form, setForm]     = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState(null);


  function openCreate() {
    setForm(EMPTY_FORM);
    setSaveErr(null);
    setModal('create');
  }

  function openEdit(item) {
    setForm({
      name:             item.name,
      description:      item.description || '',
      duration_minutes: item.duration_minutes,
      buffer_minutes:   item.buffer_minutes ?? 10,
      allow_in_person:  item.allow_in_person,
      allow_online:     item.allow_online,
      is_group:         item.is_group,
      is_active:        item.is_active,
      is_bookable:      item.is_bookable,
      display_order:    item.display_order,
    });
    setSaveErr(null);
    setModal(item);
  }

  function closeModal() { setModal(null); }

  function handleChange(field, value) {
    setForm(f => ({ ...f, [field]: value }));
  }

  // Групповой тип должен иметь ровно один формат (бэкенд проверяет XOR).
  const groupFormatInvalid =
    form.is_group && form.allow_in_person === form.allow_online;

  async function handleSave() {
    if (groupFormatInvalid) {
      setSaveErr('Для группового типа выберите ровно один формат: онлайн или очно');
      return;
    }
    setSaving(true);
    setSaveErr(null);
    try {
      if (modal === 'create') {
        await createMeetingType(form);
      } else {
        await updateMeetingType(modal.id, form);
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
      await updateMeetingType(item.id, { is_active: !item.is_active });
      refetch();
    } catch { /* ignore */ }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.pageTitle}>Типы <em>встреч</em></h1>
          <p className={styles.pageSub}>Форматы консультаций и групповых занятий.</p>
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
          label="Типы встреч"
          items={items}
          getKey={(item) => item.id}
          loading={loading}
          emptyText="Нет типов встреч. Создайте первый тип консультации."
          identity={{
            header: 'Тип встречи',
            primary: (item) => item.name,
          }}
          status={{
            header: 'Доступность',
            render: (item) => (
              <>
                <Badge tone={item.is_active ? 'success' : 'neutral'}>
                  {item.is_active ? 'Активен' : 'Отключён'}
                </Badge>
                <Badge tone="neutral">{item.is_bookable ? 'Запись открыта' : 'Запись закрыта'}</Badge>
              </>
            ),
          }}
          columns={[
            {
              key: 'params',
              header: 'Параметры',
              render: (item) => (
                <span className={styles.params}>
                  <span className={styles.nowrap}>{durationText(item)}</span>
                  <br />
                  {formatText(item)}
                  <span aria-hidden="true"> · </span>
                  <span className={item.is_group ? styles.group : undefined}>{kindText(item)}</span>
                </span>
              ),
            },
          ]}
          meta={(item) => [
            { label: 'Длительность', value: durationText(item) },
            { label: 'Формат', value: formatText(item) },
            { label: 'Тип', value: kindText(item) },
          ]}
          actions={{
            primary: (item) => (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => openEdit(item)}
                aria-label={`Изменить ${item.name}`}
              >
                Изменить
              </Button>
            ),
            menu: (item) => (
              <ActionsMenu
                triggerLabel={`Другие действия: ${item.name}`}
                items={[item.is_active
                  ? { id: 'toggle', label: 'Отключить', onSelect: () => toggleActive(item) }
                  : { id: 'toggle', label: 'Включить', tone: 'success', onSelect: () => toggleActive(item) }]}
              />
            ),
          }}
        />
      )}

      <Modal
        open={!!modal}
        onClose={closeModal}
        ariaLabel={modal === 'create' ? 'Новый тип встречи' : 'Редактировать тип встречи'}
        size="md"
      >
        <div className={styles.modalBody}>
        <h2 className={styles.modalTitle}>
          {modal === 'create' ? 'Новый тип встречи' : 'Редактировать тип встречи'}
        </h2>

        <div className={styles.formField}>
          <label className={styles.formLabel}>Название</label>
          <input
            className={styles.formInput}
            type="text"
            value={form.name}
            onChange={e => handleChange('name', e.target.value)}
            placeholder="Индивидуальная консультация"
          />
        </div>

        <div className={styles.formField}>
          <label className={styles.formLabel}>Описание</label>
          <textarea
            className={styles.formTextarea}
            value={form.description}
            onChange={e => handleChange('description', e.target.value)}
            placeholder="Краткое описание формата встречи"
            rows={3}
          />
        </div>

        <div className={styles.formRow}>
          <div className={styles.formField}>
            <label className={styles.formLabel}>Длительность (мин)</label>
            <input
              className={styles.formInput}
              type="number"
              min={10}
              max={480}
              value={form.duration_minutes}
              onChange={e => handleChange('duration_minutes', Number(e.target.value))}
            />
          </div>
          <div className={styles.formField}>
            <label className={styles.formLabel}>Буфер после встречи (мин)</label>
            <input
              className={styles.formInput}
              type="number"
              min={0}
              max={120}
              value={form.buffer_minutes}
              onChange={e => handleChange('buffer_minutes', Number(e.target.value))}
            />
          </div>
        </div>

        <div className={styles.checkboxGroup}>
          <Checkbox
            checked={form.allow_online}
            onChange={v => handleChange('allow_online', v)}
            label="Онлайн"
          />
          <Checkbox
            checked={form.allow_in_person}
            onChange={v => handleChange('allow_in_person', v)}
            label="Очно"
          />
          <Checkbox
            checked={form.is_bookable}
            onChange={v => handleChange('is_bookable', v)}
            label="Доступен для записи"
          />
          <Checkbox
            checked={form.is_group}
            onChange={v => handleChange('is_group', v)}
            label="Групповой формат"
          />
          <Checkbox
            checked={form.is_active}
            onChange={v => handleChange('is_active', v)}
            label="Активен"
          />
        </div>

        {form.is_group && (
          <p className={styles.formHint}>
            Групповой тип должен иметь ровно один формат: онлайн или очно.
          </p>
        )}

        {saveErr && <div className={styles.saveErr}>{saveErr}</div>}

        <div className={styles.modalActions}>
          <Button type="button" variant="secondary" onClick={closeModal}>Отмена</Button>
          <Button
            type="button"
            variant="primary"
            disabled={saving || !form.name.trim() || groupFormatInvalid}
            onClick={handleSave}
          >
            {saving ? 'Сохраняем…' : 'Сохранить'}
          </Button>
        </div>
        </div>
      </Modal>
    </div>
  );
}
