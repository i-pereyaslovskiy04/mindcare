import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { SECTION_PERSONAL, sectionFromHash } from '../lib/sections';

/**
 * Активный раздел настроек. Начальный раздел и переходы по ссылкам-якорям
 * (`#student-verification` → «Личные данные») берутся из location.hash;
 * выбор вкладки пользователем hash не меняет. `visited` — разделы, которые
 * хотя бы раз открывали: данные раздела «Контакты» запрашиваются лениво.
 */
export default function useSettingsSection() {
  const { hash } = useLocation();
  const [active, setActive] = useState(() => sectionFromHash(hash) ?? SECTION_PERSONAL);
  const [visited, setVisited] = useState(() => new Set([sectionFromHash(hash) ?? SECTION_PERSONAL]));
  const [seenHash, setSeenHash] = useState(hash);

  // Смена hash при уже открытой странице (переход по ссылке) — «adjust state
  // during render»: панель переключается до отрисовки, без лишнего кадра.
  if (hash !== seenHash) {
    setSeenHash(hash);
    const next = sectionFromHash(hash);
    if (next && next !== active) {
      setActive(next);
      setVisited((v) => new Set(v).add(next));
    }
  }

  const select = (id) => {
    setActive(id);
    setVisited((v) => (v.has(id) ? v : new Set(v).add(id)));
  };

  return { active, select, visited };
}
