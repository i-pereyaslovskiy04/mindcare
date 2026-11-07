import { useCallback, useEffect, useState } from 'react';
import { submitPublicCampaign } from '../../../api/campaigns.api';
import {
  buildSubmitBody, clearDraft, loadDraft, saveDraft, unansweredQuestions,
  validateProfile,
} from '../lib/draft';

/**
 * Состояние прохождения кампании: шаг (profile → questions → done), черновик
 * в sessionStorage, проверка и отправка.
 *
 * onConsentOutdated — backend сообщил, что текст согласия обновился: черновик
 * сохраняется, согласие снимается, вызывающий перезагружает анкету.
 * accessCode — кодовое слово ссылки (если задано), уходит в отправку;
 * onAccessCodeRejected — слово сменили во время прохождения (403): черновик
 * сохраняется, вызывающий снова показывает поле слова.
 */
export default function useCampaignForm(token, campaign, {
  onConsentOutdated, accessCode = null, onAccessCodeRejected,
} = {}) {
  const [draft, setDraft] = useState(() => loadDraft(token));
  const [step, setStep] = useState('profile');
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [missing, setMissing] = useState([]);

  useEffect(() => {
    if (step !== 'done') saveDraft(token, draft);
  }, [token, draft, step]);

  const setField = useCallback((name, value) => {
    setDraft((d) => ({ ...d, [name]: value }));
    setErrors((e) => (e[name] ? { ...e, [name]: undefined } : e));
  }, []);

  const setAnswer = useCallback((questionId, optionId) => {
    setDraft((d) => ({ ...d, answers: { ...d.answers, [questionId]: optionId } }));
    setMissing((m) => m.filter((id) => id !== questionId));
  }, []);

  /** К вопросам; возвращает ошибки анкеты ({} — переход выполнен). */
  const goToQuestions = useCallback(() => {
    const found = validateProfile(draft);
    setErrors(found);
    if (Object.keys(found).length) return found;
    setSubmitError(null);
    setStep('questions');
    return found;
  }, [draft]);

  const backToProfile = useCallback(() => setStep('profile'), []);

  /** Отправка; возвращает id первого неотвеченного вопроса или null. */
  const submit = useCallback(async () => {
    if (!campaign || submitting) return null;
    const left = unansweredQuestions(draft, campaign.questions);
    setMissing(left);
    if (left.length) {
      setSubmitError(`Осталось ответить на вопросов: ${left.length}`);
      return left[0];
    }
    const profileErrors = validateProfile(draft);
    if (Object.keys(profileErrors).length) {
      setErrors(profileErrors);
      setStep('profile');
      return null;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const body = buildSubmitBody(draft, campaign);
      await submitPublicCampaign(token, accessCode ? { ...body, access_code: accessCode } : body);
      clearDraft(token);
      setStep('done');
    } catch (err) {
      if (err?.status === 409 && err?.code === 'consent_outdated') {
        setDraft((d) => ({ ...d, consentAccepted: false }));
        setErrors({ consent: 'Текст согласия обновился — прочитайте его и подтвердите снова' });
        setStep('profile');
        onConsentOutdated?.();
      } else if (err?.status === 403 && err?.code === 'access_code_invalid') {
        setSubmitError('Кодовое слово изменилось. Уточните новое у организаторов и введите его — ответы сохранены на этой странице.');
        onAccessCodeRejected?.();
      } else if (err?.status === 409 && err?.code === 'campaign_not_started') {
        setSubmitError('Тестирование ещё не началось. Ответы сохранены на этой странице.');
      } else if (err?.status === 404) {
        setSubmitError('Ссылка недействительна или опрос уже завершён. Ответы не сохранены.');
      } else if (err?.status === 422) {
        setSubmitError('Проверьте анкету и ответы: сервер не принял часть данных.');
      } else if (err?.status === 503) {
        setSubmitError('Сервис временно не может сохранить ответы. Попробуйте через минуту — ответы сохранены на этой странице.');
      } else if (err?.status === 429) {
        setSubmitError('Сейчас слишком много отправок. Подождите пару минут и нажмите «Отправить» снова — ответы сохранены на этой странице.');
      } else {
        setSubmitError('Не удалось отправить ответы. Проверьте соединение и попробуйте ещё раз — ответы сохранены на этой странице.');
      }
    } finally {
      setSubmitting(false);
    }
    return null;
  }, [campaign, draft, submitting, token, onConsentOutdated, accessCode, onAccessCodeRejected]);

  return {
    draft, step, errors, missing, submitting, submitError,
    setField, setAnswer, goToQuestions, backToProfile, submit,
  };
}
