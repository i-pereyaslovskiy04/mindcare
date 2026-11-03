import { useEffect, useState } from 'react';
import styles from './AuthModal.module.css';
import { VKIcon, YandexIcon } from '../../../components/icons';
import { oauthStart } from '../../../api/auth.api';
import { getPublicConfig, socialProvidersOf } from '../../../api/config.api';
import {
  isSafeAuthorizeUrl,
  navigateToProvider,
  rememberOAuthProvider,
  startErrorMessage,
} from '../lib/oauthCallback';

// Порядок и подписи кнопок — как раньше: VK, затем Яндекс. Доступное имя
// содержит видимую подпись (WCAG 2.5.3 Label in Name) и не обещает ни вход,
// ни регистрацию: что произойдёт, решает backend.
const BUTTONS = Object.freeze([
  { provider: 'vk', label: 'VK', ariaLabel: 'Продолжить через VK', Icon: VKIcon },
  { provider: 'yandex', label: 'Яндекс', ariaLabel: 'Продолжить через Яндекс', Icon: YandexIcon },
]);

/**
 * Блок «Продолжить через» — один на всю AuthModal, над вкладками «Вход |
 * Регистрация» (Stage Social Auth 4, VK-1A). Кнопка провайдера запускает
 * ОДИН поток `oauthStart(provider)`: backend после callback сам решает, вход
 * это или продолжение регистрации. Активная вкладка в поток не передаётся.
 *
 * Кнопка активна, только если backend реально зарегистрировал адаптер
 * (GET /api/public/config → social_providers); иначе видима, но disabled и
 * запросов не шлёт. Пока идёт старт одного провайдера, вторая кнопка тоже
 * заблокирована: два параллельных старта перезаписали бы общий state-cookie.
 */
export default function SocialButtons() {
  // Пока список не получен или запрос упал — кнопки disabled; формы входа и
  // регистрации по email работают независимо.
  const [providers, setProviders] = useState([]);
  // Имя провайдера, для которого сейчас идёт старт (или null).
  const [starting, setStarting] = useState(null);
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

  const start = async (provider) => {
    if (starting !== null || !providers.includes(provider)) return;
    setError('');
    setStarting(provider);
    try {
      const data = await oauthStart(provider);
      const url = data?.authorize_url;
      if (!isSafeAuthorizeUrl(url)) throw new Error('invalid authorize_url');
      // Только ИМЯ провайдера — для текстов страницы callback. State привязан
      // HttpOnly-cookie: ни адрес, ни state на клиенте не сохраняются.
      rememberOAuthProvider(provider);
      // Top-level переход на страницу провайдера.
      navigateToProvider(url);
    } catch (err) {
      setError(startErrorMessage(err, provider));
      setStarting(null);
    }
  };

  return (
    <>
      <div className={styles.socialSection}>
        <div className={styles.socialLabel}>Продолжить через</div>
        <div className={styles.socialBtns}>
          {BUTTONS.map(({ provider, label, ariaLabel, Icon }) => {
            const available = providers.includes(provider);
            const busy = starting === provider;
            return (
              <button
                key={provider}
                type="button"
                className={styles.socBtn}
                aria-label={ariaLabel}
                title={available ? undefined : 'Сейчас недоступно'}
                onClick={() => start(provider)}
                disabled={!available || starting !== null}
                aria-busy={busy ? 'true' : undefined}
              >
                <div className={styles.socBtnIcon} aria-hidden="true"><Icon /></div>
                <span className={styles.socBtnLabel}>
                  {busy ? 'Переход…' : label}
                </span>
              </button>
            );
          })}
        </div>
        {error && (
          <div className={styles.apiError} role="alert">{error}</div>
        )}
      </div>

      <div className={styles.authDivider}>
        <div className={styles.authDividerLine} />
        <span className={styles.authDividerText}>или по email</span>
        <div className={styles.authDividerLine} />
      </div>
    </>
  );
}
