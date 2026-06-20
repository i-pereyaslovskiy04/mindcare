import { useCallback, useEffect, useState } from 'react';
import Icon from '../../components/Icon/Icon';
import Badge from '../../components/UI/Badge/Badge';
import Button from '../../components/UI/Button/Button';
import Select from '../../components/UI/Select/Select';
import DateTimeInput from '../../components/UI/DateTimeInput';
import Modal from '../../components/Modal/Modal';
import {
  getSupervisorGroupSessions,
  setGroupSessionBooking,
  createGroupSession,
  updateGroupSession,
  getMeetingTypes,
  getSupervisorPsychologists,
} from '../../api/appointments.api';
import { localToMskIso, mskIsoToLocal } from '../../utils/datetime';
import styles from './GroupSessionsPage.module.css';

// Moscow is UTC+3
function fmtDatetime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('ru-RU', {
    timeZone: 'Europe/Moscow',
    day: 'numeric', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

const STATUS_LABEL = {
  scheduled: 'Запланировано',
  completed: 'Завершено',
  cancelled: 'Отменено',
};
const STATUS_TONE = { scheduled: 'success', completed: 'neutral', cancelled: 'error' };
const FORMAT_LABEL = { online: 'Онлайн', in_person: 'Очно' };

const EMPTY_FORM = {
  meeting_type_id: '',
  psychologist_id: '',
  title: '',
  description: '',
  starts_at: '',
  ends_at: '',
  format: 'online',
  capacity: 10,
};

function useGroupSessions() {
  const [items, setItems]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const [page, setPage]       = useState(1);

  const load = useCallback(async (p) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getSupervisorGroupSessions({ page: p, size: 20 });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      setError(e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(page); }, [page, load]);

  return { items, total, loading, error, page, setPage, refetch: () => load(page) };
}

export default function GroupSessionsPage() {
  const { items, total, loading, error, page, setPage, refetch } = useGroupSessions();
  const [toggling, setToggling] = useState(null);

  // Modal state
  const [modal, setModal]     = useState(null); // null | 'create' | item
  const [form, setForm]       = useState(EMPTY_FORM);
  const [saving, setSaving]   = useState(false);
  const [saveErr, setSaveErr] = useState(null);

  // Auxiliary data for form dropdowns
  const [meetingTypes, setMeetingTypes]       = useState([]);
  const [psychologists, setPsychologists]     = useState([]);

  const totalPages = Math.max(1, Math.ceil(total / 20));

  // Load meeting types (group only) and psychologists when modal opens
  async function openCreate() {
    await loadFormData();
    setForm(EMPTY_FORM);
    setSaveErr(null);
    setModal('create');
  }

  async function openEdit(item) {
    await loadFormData();
    setForm({
      meeting_type_id: String(item.meeting_type_id || ''),
      psychologist_id: String(item.psychologist_id || ''),
      title:           item.title || '',
      description:     item.description || '',
      starts_at:       mskIsoToLocal(item.starts_at),
      ends_at:         mskIsoToLocal(item.ends_at),
      format:          item.format || 'online',
      capacity:        item.capacity || 10,
    });
    setSaveErr(null);
    setModal(item);
  }

  async function loadFormData() {
    try {
      const [mtData, psychData] = await Promise.all([
        getMeetingTypes(),
        getSupervisorPsychologists(),
      ]);
      const allTypes = mtData.items || mtData || [];
      setMeetingTypes(allTypes.filter(mt => mt.is_group));
      setPsychologists(psychData.items || psychData || []);
    } catch { /* ignore — form still usable */ }
  }

  function closeModal() { setModal(null); }

  function handleChange(field, value) {
    setForm(f => ({ ...f, [field]: value }));
  }

  // When the meeting type changes, keep the format valid for that type.
  function onMeetingTypeChange(value) {
    const mt = meetingTypes.find(m => String(m.id) === String(value));
    setForm(f => {
      let fmt = f.format;
      if (mt) {
        const allowed = [];
        if (mt.allow_online) allowed.push('online');
        if (mt.allow_in_person) allowed.push('in_person');
        if (!allowed.includes(fmt)) fmt = allowed[0] || 'online';
      }
      return { ...f, meeting_type_id: value, format: fmt };
    });
  }

  async function handleSave() {
    if (!form.starts_at) { setSaveErr('Укажите дату и время начала'); return; }
    // ends_at (если указан) должен быть строго позже starts_at
    if (form.ends_at && form.ends_at <= form.starts_at) {
      setSaveErr('Время окончания должно быть позже времени начала');
      return;
    }
    setSaving(true);
    setSaveErr(null);
    try {
      const payload = {
        meeting_type_id: Number(form.meeting_type_id),
        psychologist_id: Number(form.psychologist_id),
        title:           form.title || null,
        description:     form.description || null,
        starts_at:       localToMskIso(form.starts_at),
        ends_at:         form.ends_at ? localToMskIso(form.ends_at) : null,
        format:          form.format,
        capacity:        Number(form.capacity),
      };
      if (modal === 'create') {
        await createGroupSession(payload);
      } else {
        await updateGroupSession(modal.uuid, payload);
      }
      closeModal();
      refetch();
    } catch (e) {
      setSaveErr(e.message || 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  }

  async function toggleBooking(item) {
    setToggling(item.uuid);
    try {
      await setGroupSessionBooking(item.uuid, !item.booking_enabled);
      refetch();
    } catch { /* ignore */ }
    finally { setToggling(null); }
  }

  const selectedMt = meetingTypes.find(
    mt => String(mt.id) === String(form.meeting_type_id)
  );
  const allowedFormats = selectedMt
    ? [
        selectedMt.allow_online    && { value: 'online',    label: 'Онлайн' },
        selectedMt.allow_in_person && { value: 'in_person', label: 'Очно' },
      ].filter(Boolean)
    : [
        { value: 'online',    label: 'Онлайн' },
        { value: 'in_person', label: 'Очно' },
      ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.labelTag}>Супервизор</div>
          <h1 className={styles.pageTitle}>Групповые <em>занятия</em></h1>
          <p className={styles.pageSub}>Управление расписанием групповых сессий.</p>
        </div>
        <Button type="button" variant="primary" onClick={openCreate}>
          <Icon name="plus" size={14} /> Добавить
        </Button>
      </div>

      {loading && <div className={styles.hint}>Загрузка…</div>}

      {!loading && error && (
        <div className={styles.stateBox}>
          <div className={styles.stateTitle}>Ошибка загрузки</div>
          <div className={styles.stateSub}>{error}</div>
          <Button variant="secondary" type="button" onClick={refetch}>Повторить</Button>
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className={styles.stateBox}>
          <Icon name="calendar" size={36} />
          <div className={styles.stateTitle}>Нет групповых занятий</div>
          <div className={styles.stateSub}>Создайте первое занятие.</div>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <>
          <div className={styles.list}>
            {items.map(gs => (
              <div key={gs.uuid} className={styles.card}>
                <div className={styles.cardTop}>
                  <div className={styles.cardTitle}>
                    {gs.title || gs.meeting_type_name || 'Групповое занятие'}
                  </div>
                  <div className={styles.cardBadges}>
                    <Badge tone={STATUS_TONE[gs.status] || 'neutral'}>
                      {STATUS_LABEL[gs.status] || gs.status}
                    </Badge>
                    {gs.booking_enabled
                      ? <Badge tone="success">Запись открыта</Badge>
                      : <Badge tone="neutral">Запись закрыта</Badge>
                    }
                  </div>
                </div>

                {gs.description && (
                  <div className={styles.cardDesc}>{gs.description}</div>
                )}

                <div className={styles.cardMeta}>
                  <span className={styles.metaItem}>
                    <Icon name="calendar" size={13} />
                    {fmtDatetime(gs.starts_at)}
                    {gs.ends_at ? ` — ${fmtDatetime(gs.ends_at)}` : ''}
                  </span>
                  <span className={styles.metaItem}>
                    <Icon name="users" size={13} />
                    {gs.registered_count} / {gs.capacity} мест
                  </span>
                  <span className={styles.metaItem}>
                    {FORMAT_LABEL[gs.format] || gs.format}
                  </span>
                  {gs.psychologist_name && (
                    <span className={styles.metaItem}>
                      <Icon name="bell" size={13} />
                      {gs.psychologist_name}
                    </span>
                  )}
                </div>

                <div className={styles.cardActions}>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => openEdit(gs)}
                  >
                    Изменить
                  </Button>
                  <Button
                    type="button"
                    variant={gs.booking_enabled ? 'ghost' : 'secondary'}
                    size="sm"
                    disabled={toggling === gs.uuid}
                    onClick={() => toggleBooking(gs)}
                  >
                    {toggling === gs.uuid
                      ? '…'
                      : gs.booking_enabled
                        ? 'Закрыть запись'
                        : 'Открыть запись'}
                  </Button>
                </div>
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className={styles.pagination}>
              <Button
                type="button" variant="icon" size="sm"
                aria-label="Предыдущая страница"
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
              >
                <Icon name="chevron-left" size={16} />
              </Button>
              <span className={styles.pageInfo}>{page} / {totalPages}</span>
              <Button
                type="button" variant="icon" size="sm"
                aria-label="Следующая страница"
                disabled={page === totalPages}
                onClick={() => setPage(p => p + 1)}
              >
                <Icon name="chevron-right" size={16} />
              </Button>
            </div>
          )}
          <div className={styles.totalHint}>Всего занятий: {total}</div>
        </>
      )}

      {/* Create / Edit modal */}
      <Modal
        open={!!modal}
        onClose={closeModal}
        ariaLabel={modal === 'create' ? 'Новое групповое занятие' : 'Изменить занятие'}
        size="md"
      >
        <div className={styles.modalBody}>
        <h2 className={styles.modalTitle}>
          {modal === 'create' ? 'Новое групповое занятие' : 'Изменить занятие'}
        </h2>

        {/* Meeting type */}
        <div className={styles.formField}>
          <Select
            label="Тип занятия"
            placeholder="— выберите тип —"
            value={form.meeting_type_id}
            options={meetingTypes.map(mt => ({
              value: String(mt.id), label: mt.name,
            }))}
            onChange={onMeetingTypeChange}
          />
        </div>

        {/* Psychologist */}
        <div className={styles.formField}>
          <Select
            label="Психолог"
            placeholder="— выберите психолога —"
            value={form.psychologist_id}
            options={psychologists.map(p => ({
              value: String(p.id), label: p.full_name || p.email,
            }))}
            onChange={v => handleChange('psychologist_id', v)}
          />
        </div>

        {/* Title */}
        <div className={styles.formField}>
          <label className={styles.formLabel}>Название (необязательно)</label>
          <input
            className={styles.formInput}
            type="text"
            value={form.title}
            onChange={e => handleChange('title', e.target.value)}
            placeholder="Например: Группа поддержки"
          />
        </div>

        {/* Description */}
        <div className={styles.formField}>
          <label className={styles.formLabel}>Описание (необязательно)</label>
          <textarea
            className={styles.formInput}
            rows={3}
            value={form.description}
            onChange={e => handleChange('description', e.target.value)}
            placeholder="О чём занятие, для кого, что взять с собой…"
          />
        </div>

        {/* Dates: дата + время через shared DateTimeInput (МСК). */}
        <div className={styles.formRow}>
          <div className={styles.formField}>
            <DateTimeInput
              label="Начало (МСК)"
              value={form.starts_at}
              onChange={v => handleChange('starts_at', v)}
            />
          </div>
          <div className={styles.formField}>
            <DateTimeInput
              label="Конец (МСК, необязательно)"
              value={form.ends_at}
              onChange={v => handleChange('ends_at', v)}
            />
          </div>
        </div>

        {/* Format and capacity */}
        <div className={styles.formRow}>
          <div className={styles.formField}>
            <Select
              label="Формат"
              value={form.format}
              options={allowedFormats}
              onChange={v => handleChange('format', v)}
            />
          </div>
          <div className={styles.formField}>
            <label className={styles.formLabel}>Мест</label>
            <input
              className={styles.formInput}
              type="number"
              min={1}
              max={200}
              value={form.capacity}
              onChange={e => handleChange('capacity', Number(e.target.value))}
            />
          </div>
        </div>

        {saveErr && <div className={styles.saveErr}>{saveErr}</div>}

        <div className={styles.modalActions}>
          <Button type="button" variant="secondary" onClick={closeModal}>
            Отмена
          </Button>
          <Button
            type="button"
            variant="primary"
            disabled={saving || !form.meeting_type_id || !form.psychologist_id || !form.starts_at}
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
