import { useId, useState } from 'react';
import {
  deleteCampaign, downloadCampaignResults, renameCampaign, rotateCampaignLink,
  setCampaignStatus,
} from '../../../api/campaigns.api';
import { saveBlobToDisk } from '../../../api/client';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import TextField from '../../../components/UI/TextField/TextField';
import ConfirmDialog from '../../assignments/ui/ConfirmDialog';
import CampaignAccessPanel from './CampaignAccessPanel';
import CampaignResponses from './CampaignResponses';
import CampaignResults from './CampaignResults';
import styles from './CampaignCard.module.css';

export function campaignLink(campaign) {
  if (campaign.link_url) return campaign.link_url;
  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  return `${origin}${campaign.link_path}`;
}

export function exportFilename(title) {
  const safe = String(title || 'кампания').replace(/[\\/:*?"<>|\s]+/g, '_').slice(0, 80);
  return `Результаты_${safe}.xlsx`;
}

function formatDate(value) {
  return value ? new Date(value).toLocaleDateString('ru-RU') : '';
}

const MSK = { timeZone: 'Europe/Moscow', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' };

function formatMsk(value) {
  return new Date(value).toLocaleString('ru-RU', MSK);
}

// Что сейчас видит участник по ссылке (link_state с backend).
const LINK_STATE = {
  open: { label: 'Открыта', tone: 'success' },
  scheduled: { label: 'Ещё не началась', tone: 'warning' },
  expired: { label: 'Срок истёк', tone: 'neutral' },
  closed: { label: 'Закрыта', tone: 'neutral' },
};

const DIALOGS = {
  rotate: {
    title: 'Выпустить новую ссылку?',
    description: 'Старая ссылка сразу перестанет работать. Уже полученные ответы сохранятся.',
    confirmLabel: 'Выпустить',
    tone: 'primary',
  },
  delete: {
    title: 'Удалить кампанию?',
    description: 'Кампания, все ответы участников и записи их согласий будут удалены безвозвратно. Перед удалением скачайте результаты.',
    confirmLabel: 'Удалить',
    tone: 'danger',
  },
};

/**
 * Кампания: статус, ссылка (копировать), переименование (адрес ссылки не
 * меняется), скачать xlsx, закрыть/открыть, новая ссылка, участники, удаление. Без оптимистичного успеха: карточка
 * обновляется ответом backend (onChange) или удаляется (onDeleted).
 */
export default function CampaignCard({ campaign, onChange, onDeleted }) {
  const baseId = useId();
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [dialogError, setDialogError] = useState(null);
  // Открытая панель: null | 'results' | 'responses' | 'access'.
  const [panel, setPanel] = useState(null);
  const togglePanel = (name) => setPanel((p) => (p === name ? null : name));
  // Переименование: null — не редактируется, строка — черновик названия.
  const [draftTitle, setDraftTitle] = useState(null);
  const [titleError, setTitleError] = useState(null);
  const link = campaignLink(campaign);
  const isOpen = campaign.status === 'open';
  const state = LINK_STATE[campaign.link_state] || LINK_STATE[isOpen ? 'open' : 'closed'];

  async function run(name, action) {
    setBusy(name);
    setError(null);
    setMessage(null);
    try {
      await action();
    } catch (err) {
      if (err?.name !== 'AbortError') setError(err?.message || 'Не удалось выполнить действие');
    } finally {
      setBusy(null);
    }
  }

  function copyLink() {
    run('copy', async () => {
      await navigator.clipboard.writeText(link);
      setMessage('Ссылка скопирована');
    });
  }

  function toggleStatus() {
    run('status', async () => {
      onChange(await setCampaignStatus(campaign.uuid, isOpen ? 'closed' : 'open'));
      setMessage(isOpen ? 'Кампания закрыта — ссылка больше не принимает ответы' : 'Кампания снова открыта');
    });
  }

  function startRename() {
    setDraftTitle(campaign.title);
    setTitleError(null);
    setMessage(null);
  }

  async function saveTitle(e) {
    e.preventDefault();
    const title = draftTitle.split(/\s+/).filter(Boolean).join(' ');
    if (title.length < 2) {
      setTitleError('Минимум 2 символа');
      return;
    }
    if (title === campaign.title) {
      setDraftTitle(null);
      return;
    }
    setBusy('rename');
    setTitleError(null);
    try {
      onChange(await renameCampaign(campaign.uuid, title));
      setDraftTitle(null);
      setMessage('Название изменено, ссылка прежняя');
    } catch (err) {
      setTitleError(err?.message || 'Не удалось переименовать');
    } finally {
      setBusy(null);
    }
  }

  function download() {
    run('download', async () => {
      await saveBlobToDisk(async () => {
        const { blob } = await downloadCampaignResults(campaign.uuid);
        return blob;
      }, exportFilename(campaign.title));
    });
  }

  async function confirmDialog() {
    setBusy(dialog);
    setDialogError(null);
    try {
      if (dialog === 'rotate') {
        onChange(await rotateCampaignLink(campaign.uuid));
        setMessage('Выпущена новая ссылка — отправьте её участникам');
        setDialog(null);
      } else {
        await deleteCampaign(campaign.uuid);
        setDialog(null);
        onDeleted(campaign.uuid);
      }
    } catch (err) {
      setDialogError(err?.message || 'Не удалось выполнить действие');
    } finally {
      setBusy(null);
    }
  }

  const titleId = `${baseId}-title`;
  const linkId = `${baseId}-link`;
  const current = dialog ? DIALOGS[dialog] : null;

  return (
    <article className={styles.card} aria-labelledby={titleId}>
      <header className={styles.header}>
        <div className={styles.headText}>
          {draftTitle === null ? (
            <h3 id={titleId} className={styles.title}>{campaign.title}</h3>
          ) : (
            <form className={styles.renameForm} onSubmit={saveTitle} noValidate>
              <h3 id={titleId} className={styles.visuallyHidden}>{campaign.title}</h3>
              <TextField
                label="Название"
                hint="Адрес ссылки не изменится"
                value={draftTitle}
                onChange={(e) => { setDraftTitle(e.target.value); setTitleError(null); }}
                error={titleError}
                maxLength={255}
                appearance="field"
                autoFocus
              />
              <div className={styles.renameActions}>
                <Button type="submit" loading={busy === 'rename'}>Сохранить</Button>
                <Button type="button" variant="secondary" disabled={busy === 'rename'}
                  onClick={() => setDraftTitle(null)}>
                  Отмена
                </Button>
              </div>
            </form>
          )}
          <p className={styles.meta}>
            {campaign.test_title} · создана {formatDate(campaign.created_at)}
            {campaign.closed_at && ` · закрыта ${formatDate(campaign.closed_at)}`}
          </p>
          {(campaign.opens_at || campaign.closes_at || campaign.access_code_set) && (
            <p className={styles.meta}>
              {[
                campaign.opens_at && `с ${formatMsk(campaign.opens_at)}`,
                campaign.closes_at && `до ${formatMsk(campaign.closes_at)}`,
                campaign.access_code_set && 'по кодовому слову',
              ].filter(Boolean).join(' · ')}
            </p>
          )}
        </div>
        <Badge tone={state.tone}>{state.label}</Badge>
      </header>

      <div className={styles.linkRow}>
        <label htmlFor={linkId} className={styles.linkLabel}>Ссылка для участников</label>
        <div className={styles.linkControls}>
          <input id={linkId} className={styles.linkInput} value={link} readOnly
            onFocus={(e) => e.target.select()} />
          <Button type="button" variant="secondary" onClick={copyLink}
            loading={busy === 'copy'}>
            Копировать
          </Button>
        </div>
      </div>

      <p className={styles.count}>Прошли тестирование: <strong>{campaign.responses_count}</strong></p>

      <div className={styles.actions}>
        <Button type="button" onClick={download} loading={busy === 'download'}
          disabled={!campaign.responses_count}>
          Скачать xlsx
        </Button>
        <Button type="button" variant="secondary" onClick={() => togglePanel('results')}
          aria-expanded={panel === 'results'} disabled={!campaign.responses_count}>
          {panel === 'results' ? 'Скрыть результаты' : 'Результаты'}
        </Button>
        <Button type="button" variant="secondary" onClick={() => togglePanel('responses')}
          aria-expanded={panel === 'responses'}>
          {panel === 'responses' ? 'Скрыть участников' : 'Участники'}
        </Button>
        <Button type="button" variant="secondary" onClick={() => togglePanel('access')}
          aria-expanded={panel === 'access'}>
          {panel === 'access' ? 'Скрыть сроки и код' : 'Сроки и код'}
        </Button>
        <Button type="button" variant="secondary" onClick={toggleStatus}
          loading={busy === 'status'}>
          {isOpen ? 'Закрыть' : 'Открыть снова'}
        </Button>
        <Button type="button" variant="ghost" onClick={startRename}
          disabled={draftTitle !== null}>
          Переименовать
        </Button>
        <Button type="button" variant="ghost"
          onClick={() => { setDialogError(null); setDialog('rotate'); }}>
          Новая ссылка
        </Button>
        <Button type="button" variant="danger"
          onClick={() => { setDialogError(null); setDialog('delete'); }}>
          Удалить
        </Button>
      </div>

      <div aria-live="polite" className={styles.message}>{message}</div>
      {error && <p className={styles.error} role="alert">{error}</p>}

      {panel === 'access' && (
        <div className={styles.responses}>
          <CampaignAccessPanel campaign={campaign} onChange={onChange} />
        </div>
      )}

      {panel === 'results' && (
        <div className={styles.responses}>
          <CampaignResults campaignUuid={campaign.uuid} />
        </div>
      )}

      {panel === 'responses' && (
        <div className={styles.responses}>
          <CampaignResponses
            campaignUuid={campaign.uuid}
            onDeleted={() => onChange({
              ...campaign, responses_count: Math.max(0, campaign.responses_count - 1),
            })}
          />
        </div>
      )}

      <ConfirmDialog
        open={Boolean(current)}
        title={current?.title}
        description={current?.description}
        confirmLabel={current?.confirmLabel}
        confirmTone={current?.tone}
        loading={busy === dialog && Boolean(dialog)}
        error={dialogError}
        onConfirm={confirmDialog}
        onClose={() => setDialog(null)}
      />
    </article>
  );
}
