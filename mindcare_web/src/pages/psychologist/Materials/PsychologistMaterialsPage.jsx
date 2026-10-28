import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import Tabs, { tabButtonId, tabPanelId } from '../../../components/UI/Tabs/Tabs';
import { useAuth } from '../../../features/auth/AuthContext';
import MaterialsLibrary from '../../../features/materials/ui/MaterialsLibrary';
import MyArticles from '../../../features/materials/ui/MyArticles';
import styles from './PsychologistMaterialsPage.module.css';

const psychologistMaterialPath = (id) => `/psychologist/materials/${id}`;
const TABS_PREFIX = 'psych-materials';
// Ссылка из system-сообщения о решении модерации (internalLinks.js).
const MY_MATERIALS_HASH = '#my-materials';
const TABS = [
  { id: 'library', label: 'Библиотека' },
  { id: 'mine', label: 'Мои материалы' },
];

/**
 * Материалы психолога: библиотека опубликованных материалов (чтение,
 * избранное, прикрепление к заданиям) и «Мои материалы» — свои статьи с
 * модерацией (ADR-034): черновик → на проверку → публикует супервизор.
 * В режиме «под именем» авторство и избранное недоступны. Ссылка
 * /psychologist/materials#my-materials (уведомление о решении проверяющего)
 * открывает вкладку «Мои материалы».
 */
export default function PsychologistMaterialsPage() {
  const { isImpersonating } = useAuth();
  const { hash } = useLocation();
  const [active, setActive] = useState(hash === MY_MATERIALS_HASH ? 'mine' : 'library');

  useEffect(() => {
    if (hash === MY_MATERIALS_HASH) setActive('mine');
  }, [hash]);

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>Материалы</h1>
      <p className={styles.pageSub}>
        Опубликованные материалы библиотеки и ваши собственные статьи. Свои материалы
        публикуются после проверки супервизором.
      </p>

      {isImpersonating ? (
        <MaterialsLibrary variant="compact" getItemPath={psychologistMaterialPath} />
      ) : (
        <>
          <Tabs
            tabs={TABS}
            active={active}
            onChange={setActive}
            label="Разделы материалов"
            idPrefix={TABS_PREFIX}
            className={styles.tabs}
          />
          <div
            role="tabpanel"
            id={tabPanelId(TABS_PREFIX, 'library')}
            aria-labelledby={tabButtonId(TABS_PREFIX, 'library')}
            hidden={active !== 'library'}
          >
            <MaterialsLibrary variant="compact" withFavorites getItemPath={psychologistMaterialPath} />
          </div>
          <div
            role="tabpanel"
            id={tabPanelId(TABS_PREFIX, 'mine')}
            aria-labelledby={tabButtonId(TABS_PREFIX, 'mine')}
            hidden={active !== 'mine'}
          >
            {active === 'mine' && <MyArticles />}
          </div>
        </>
      )}
    </div>
  );
}
