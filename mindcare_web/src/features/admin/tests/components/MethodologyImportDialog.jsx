import { useId, useRef, useState } from 'react';
import Modal from '../../../../components/Modal/Modal';
import Button from '../../../../components/UI/Button/Button';
import { saveBlobToDisk } from '../../../../api/client';
import {
  ADMIN_TESTS_BASE, downloadMethodologyTemplate, importMethodology,
} from '../../../../api/tests.api';
import styles from './MethodologyImportDialog.module.css';

function errorAddress(e) {
  return [e.sheet && `лист «${e.sheet}»`, e.row && `строка ${e.row}`, e.column && `колонка ${e.column}`]
    .filter(Boolean).join(', ');
}

/**
 * Импорт методики из шаблона xlsx (ADR-037): «Скачать шаблон» → выбор файла →
 * проверка на сервере (dry_run, ничего не сохраняется) → «Создать черновик».
 * Черновик открывается в конструкторе (onCreated(uuid)). Содержимое файла
 * на клиенте не разбирается и не логируется.
 */
export default function MethodologyImportDialog({ open, onClose, onCreated, base = ADMIN_TESTS_BASE }) {
  const inputId = useId();
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState('');

  function reset() {
    setFile(null);
    setReport(null);
    setError('');
    if (inputRef.current) inputRef.current.value = '';
  }

  function close() {
    if (busy) return;
    reset();
    onClose();
  }

  async function downloadTemplate() {
    setBusy('template');
    setError('');
    try {
      await saveBlobToDisk(async () => (await downloadMethodologyTemplate(base)).blob,
        'Шаблон_методики.xlsx');
    } catch (err) {
      if (err?.name !== 'AbortError') setError(err.message || 'Не удалось скачать шаблон');
    } finally {
      setBusy(null);
    }
  }

  async function check(selected) {
    setFile(selected);
    setReport(null);
    setError('');
    if (!selected) return;
    setBusy('check');
    try {
      setReport(await importMethodology(selected, { dryRun: true, base }));
    } catch (err) {
      setError(err.message || 'Не удалось проверить файл');
    } finally {
      setBusy(null);
    }
  }

  async function create() {
    setBusy('create');
    setError('');
    try {
      const res = await importMethodology(file, { base });
      reset();
      onCreated(res.test_uuid);
    } catch (err) {
      if (err?.body?.errors) setReport(err.body);
      setError(err.message || 'Не удалось создать черновик');
    } finally {
      setBusy(null);
    }
  }

  const summary = report?.summary;

  return (
    <Modal open={open} onClose={close} ariaLabel="Импорт методики из xlsx" zIndex={2200}>
      <div className={styles.body}>
        <h2 className={styles.title}>Импорт методики из xlsx</h2>
        <p className={styles.text}>
          Заполните шаблон (вопросы, варианты ответа, ключ, шкалы, уровни, типы) и загрузите его.
          Будет создан черновик: его можно проверить в конструкторе и отправить на проверку.
          Пример заполнения — «Выгрузить в xlsx» у любой методики.
        </p>
        <div className={styles.row}>
          <Button type="button" variant="secondary" onClick={downloadTemplate}
            loading={busy === 'template'}>
            Скачать шаблон
          </Button>
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor={inputId}>Файл методики (.xlsx, до 2 МБ)</label>
          <input id={inputId} ref={inputRef} className={styles.file} type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            disabled={Boolean(busy)}
            onChange={(e) => check(e.target.files?.[0] || null)} />
        </div>

        <div aria-live="polite">
          {busy === 'check' && <p className={styles.muted}>Проверяем файл…</p>}
          {report && !report.ok && (
            <div className={styles.errors} role="alert">
              <p className={styles.errorsTitle}>Файл содержит ошибки — исправьте их и загрузите снова:</p>
              <ul>
                {report.errors.map((e, i) => (
                  // eslint-disable-next-line react/no-array-index-key -- ошибки без собственного id
                  <li key={i}>
                    {errorAddress(e) && <b>{errorAddress(e)}: </b>}
                    {e.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {report?.ok && summary && (
            <div className={styles.ok}>
              <p>
                Файл в порядке: <b>{summary.title}</b> — вопросов {summary.questions},{' '}
                {summary.options != null
                  ? `вариантов ответа ${summary.options}`
                  : `наборов вариантов ответа ${summary.option_sets}`}, шкал {summary.scales}, уровней {summary.levels},
                типов {summary.types}, порогов интерпретации {summary.interpretations}.
              </p>
              {report.warnings.length > 0 && (
                <>
                  <p className={styles.warnTitle}>
                    Замечания (черновик создать можно, но на проверку он не уйдёт, пока они есть):
                  </p>
                  <ul className={styles.warnings}>
                    {report.warnings.map((w) => <li key={w}>{w}</li>)}
                  </ul>
                </>
              )}
            </div>
          )}
          {error && (!report || report.ok) && <p className={styles.error} role="alert">{error}</p>}
        </div>

        <div className={styles.actions}>
          <Button type="button" variant="secondary" onClick={close} disabled={Boolean(busy)}>
            Закрыть
          </Button>
          <Button type="button" variant="primary" onClick={create}
            disabled={!report?.ok || Boolean(busy)} loading={busy === 'create'}>
            Создать черновик
          </Button>
        </div>
      </div>
    </Modal>
  );
}
