import { useEffect, useState } from 'react';
import Modal from '../../../components/Modal/Modal';
import Button from '../../../components/UI/Button/Button';
import Select from '../../../components/UI/Select/Select';
import { getSupervisorPsychologists } from '../../../api/supervisor.api';
import styles from './AssignModal.module.css';

/**
 * Универсальное модальное окно для трёх сценариев:
 *   mode="assign"   — назначить психолога (нет текущего)
 *   mode="transfer" — переназначить (есть текущий)
 *   mode="close"    — закрыть связь
 */
export default function AssignModal({ mode, student, onConfirm, onClose }) {
  const [psychologists, setPsychologists]   = useState([]);
  const [psyLoading, setPsyLoading]         = useState(false);
  const [selectedPsyId, setSelectedPsyId]   = useState('');
  const [primaryConcern, setPrimaryConcern] = useState('');
  const [reason, setReason]                 = useState('');
  const [submitting, setSubmitting]         = useState(false);
  const [error, setError]                   = useState(null);

  const needsPsychologist = mode === 'assign' || mode === 'transfer';

  useEffect(() => {
    if (!needsPsychologist) return;
    let cancelled = false;
    setPsyLoading(true);
    getSupervisorPsychologists({ size: 200 })
      .then(data => { if (!cancelled) setPsychologists(data.items); })
      .catch(err => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setPsyLoading(false); });
    return () => { cancelled = true; };
  }, [needsPsychologist]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (needsPsychologist && !selectedPsyId) {
      setError('Выберите психолога');
      return;
    }

    setSubmitting(true);
    try {
      await onConfirm({
        selectedPsyId: selectedPsyId ? Number(selectedPsyId) : null,
        primaryConcern: primaryConcern.trim() || null,
        reason: reason.trim() || null,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  const titles = {
    assign:   'Назначить психолога',
    transfer: 'Переназначить психолога',
    close:    'Закрыть связь',
  };

  const confirmLabels = {
    assign:   'Назначить',
    transfer: 'Переназначить',
    close:    'Закрыть связь',
  };

  return (
    <Modal open onClose={onClose} size="md" ariaLabel={titles[mode]}>
      <form onSubmit={handleSubmit} className={styles.form}>
        <h2 className={styles.title}>{titles[mode]}</h2>

        {/* Информация о студенте */}
        <div className={styles.studentBlock}>
          <div className={styles.studentLabel}>Студент</div>
          <div className={styles.studentName}>{student.full_name}</div>
          <div className={styles.studentEmail}>{student.email}</div>
        </div>

        {/* Текущий психолог (для transfer/close) */}
        {(mode === 'transfer' || mode === 'close') && student.current_engagement?.psychologist && (
          <div className={styles.currentBlock}>
            <div className={styles.currentLabel}>Текущий психолог</div>
            <div className={styles.currentName}>
              {student.current_engagement.psychologist.full_name}
            </div>
          </div>
        )}

        {/* Выбор нового психолога */}
        {needsPsychologist && (
          <div className={styles.field}>
            {psyLoading ? (
              <div className={styles.psyLoading}>Загрузка психологов…</div>
            ) : (
              <Select
                label={mode === 'transfer' ? 'Новый психолог' : 'Психолог'}
                placeholder="— Выберите психолога —"
                value={selectedPsyId}
                options={psychologists.map(p => ({
                  value: p.id,
                  label: p.full_name + (p.is_accepting === false ? ' (не принимает)' : ''),
                }))}
                onChange={setSelectedPsyId}
                disabled={submitting}
              />
            )}
          </div>
        )}

        {/* Основная жалоба (только для assign) */}
        {mode === 'assign' && (
          <div className={styles.field}>
            <label className={styles.label}>Основная жалоба (необязательно)</label>
            <textarea
              className={styles.textarea}
              placeholder="Краткое описание запроса студента…"
              value={primaryConcern}
              onChange={e => setPrimaryConcern(e.target.value)}
              rows={3}
              maxLength={2000}
            />
          </div>
        )}

        {/* Причина (для transfer/close) */}
        {(mode === 'transfer' || mode === 'close') && (
          <div className={styles.field}>
            <label className={styles.label}>
              {mode === 'transfer' ? 'Причина переназначения' : 'Причина закрытия'}
              {' '}(необязательно)
            </label>
            <textarea
              className={styles.textarea}
              placeholder="Укажите причину…"
              value={reason}
              onChange={e => setReason(e.target.value)}
              rows={3}
              maxLength={2000}
            />
          </div>
        )}

        {error && <div className={styles.error}>{error}</div>}

        <div className={styles.actions}>
          <Button
            variant="ghost"
            onClick={onClose}
            disabled={submitting}
          >
            Отмена
          </Button>
          <Button
            type="submit"
            variant={mode === 'close' ? 'danger' : 'primary'}
            disabled={submitting}
          >
            {submitting ? 'Выполняется…' : confirmLabels[mode]}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
