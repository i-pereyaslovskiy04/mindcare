import { useEffect, useState } from 'react';
import styles from './AuthModal.module.css';
import { VKIcon, YandexIcon } from '../../../components/icons';
import { oauthStart } from '../../../api/auth.api';
import { getPublicConfig, socialProvidersOf } from '../../../api/config.api';
import {
  isSafeAuthorizeUrl,
  navigateToProvider,
  startErrorMessage,
} from '../lib/oauthCallback';

/**
 * Блок «Быстрая авторизация» — общий для вкладок «Вход» и «Регистрация»
 * (Stage Social Auth 4). Кнопка Яндекса в обеих вкладках запускает ОДИН и тот
 * же поток: backend после callback сам решает, вход это (identity уже
 * привязана) или продолжение регистрации (identity новая). Отдельного
 * «намерения» вкладка не передаёт.
 *
 *   Яндекс — активна, только если backend реально зарегистрировал адаптер
 *            (GET /api/public/config → social_providers); иначе видима, но
 *            disabled.
 *   VK     — видимая заглушка: всегда disabled, запросов не шлёт (адаптера
 *            ещё нет — отдельный этап).
 */
export default function SocialButtons() {
  // Пока список не получен или запрос упал — Яндекс disabled; формы входа и
  // регистрации по email работают независимо.
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    getPublicConfig()
      .then((config) => {
        if (!cancelled) setProviders(socialProvidersOf(config));
      })
      .catch(() => {
        if (!cancelled) setProviders([]);
      });
    return () => { cancelled = true; };
  }, []);

  const yandexAvailable = providers.includes('yandex');

  const handleYandex = async () => {
    if (loading || !yandexAvailable) return;
    setError('');
    setLoading(true);
    try {
      const data = await oauthStart('yandex');
      const url = data?.authorize_url;
      if (!isSafeAuthorizeUrl(url)) throw new Error('invalid authorize_url');
      // Top-level переход на страницу Яндекса; state привязан HttpOnly-cookie,
      // поэтому ни адрес, ни state нигде на клиенте не сохраняются.
      navigateToProvider(url);
    } catch (err) {
      setError(startErrorMessage(err));
      setLoading(false);
    }
  };

  return (
    <>
      <div className={styles.socialSection}>
        <div className={styles.socialLabel}>Быстрая авторизация</div>
        <div className={styles.socialBtns}>
          <button
            type="button"
            className={styles.socBtn}
            aria-label="Войти через ВКонтакте (скоро)"
            title="Скоро"
            disabled
          >
            <div className={styles.socBtnIcon} aria-hidden="true"><VKIcon /></div>
            <span className={styles.socBtnLabel}>VK</span>
          </button>
          <button
            type="button"
            className={styles.socBtn}
            aria-label="Войти через Яндекс"
            title={yandexAvailable ? undefined : 'Сейчас недоступно'}
            onClick={handleYandex}
            disabled={!yandexAvailable || loading}
            aria-busy={loading ? 'true' : undefined}
          >
            <div className={styles.socBtnIcon} aria-hidden="true"><YandexIcon /></div>
            <span className={styles.socBtnLabel}>
              {loading ? 'Переход…' : 'Яндекс'}
            </span>
          </button>
        </div>
        {error && (
          <div className={styles.apiError} role="alert">{error}</div>
        )}
      </div>

      <div className={styles.authDivider}>
        <div className={styles.authDividerLine} />
        <span className={styles.authDividerText}>или продолжить с email</span>
        <div className={styles.authDividerLine} />
      </div>
    </>
  );
}
