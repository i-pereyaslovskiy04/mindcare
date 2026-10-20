import { useState, useMemo, useEffect } from 'react';

const ARTICLES = [
  { id: 1,  title: 'Когда тревога говорит правду — а когда обманывает', topic: 'Тревога',    tag: 'Статья',    description: 'Как отличить тревогу-сигнал от тревоги-помехи и перестать верить каждой тревожной мысли.',                 date: '24 апр 2025', time: '7 мин'  },
  { id: 2,  title: 'Почему мы просыпаемся в 4 утра. Спокойный взгляд',  topic: 'Сон',       tag: 'Статья',    description: 'Нейробиологические причины ночных пробуждений и практические шаги к восстановлению сна.',             date: '21 апр 2025', time: '5 мин'  },
  { id: 3,  title: 'Дыхание 4-7-8: короткая практика на каждый день',    topic: 'Стресс',    tag: 'Упражнение',description: 'Пошаговая техника дыхания для быстрого снижения тревоги и стресса в любой ситуации.',                 date: '19 апр 2025', time: '3 мин'  },
  { id: 4,  title: 'Как просить о поддержке, когда не умеешь',           topic: 'Отношения', tag: 'Статья',    description: 'Практическое руководство: как попросить о помощи без стыда и страха быть отвергнутым.',              date: '15 апр 2025', time: '9 мин'  },
  { id: 5,  title: 'Гнев как сигнал, а не враг',                         topic: 'Эмоции',    tag: 'Статья',    description: 'Как перестать подавлять гнев и научиться использовать его энергию конструктивно.',                   date: '12 апр 2025', time: '6 мин'  },
  { id: 6,  title: 'Внутренний критик: научиться разговаривать иначе',   topic: 'Самооценка',tag: 'Статья',    description: 'Откуда берётся внутренний критик и как изменить с ним отношения, не заглушая его.',                 date: '8 апр 2025',  time: '8 мин'  },
  { id: 7,  title: 'Гигиена сна: что действительно работает',            topic: 'Сон',       tag: 'Гид',       description: 'Доказательные рекомендации по улучшению качества сна при стрессе и интенсивной нагрузке.',         date: '4 апр 2025',  time: '5 мин'  },
  { id: 8,  title: 'Заземление 5-4-3-2-1: вернуться в настоящее',        topic: 'Тревога',   tag: 'Упражнение',description: 'Техника сенсорного заземления для быстрого выхода из тревожного состояния.',                         date: '1 апр 2025',  time: '2 мин'  },
  { id: 9,  title: 'Стресс и тело: как напряжение живёт в нас',          topic: 'Стресс',    tag: 'Статья',    description: 'Как хронический стресс меняет тело и что с этим делать на практике.',                               date: '28 мар 2025', time: '6 мин'  },
  { id: 10, title: 'Самосострадание: относиться к себе по-другому',      topic: 'Самооценка',tag: 'Вебинар',   description: 'Запись вебинара о практике самосострадания как основе психологической устойчивости.',               date: '24 мар 2025', time: '7 мин'  },
  { id: 11, title: 'Эмоциональные границы в близких отношениях',         topic: 'Отношения', tag: 'Вебинар',   description: 'Как выстраивать границы без вины и конфликта: разбор реальных ситуаций.',                           date: '20 мар 2025', time: '10 мин' },
  { id: 12, title: 'Дневник эмоций: зачем и как вести',                  topic: 'Эмоции',    tag: 'Гид',       description: 'Практическое руководство по ведению дневника эмоций для лучшего понимания себя.',                  date: '16 мар 2025', time: '5 мин'  },
];

const PAGE_SIZE = 8;

export function useStudentMaterials() {
  const [query,          setQuery]          = useState('');
  const [selectedTags,   setSelectedTags]   = useState([]);
  const [selectedTopics, setSelectedTopics] = useState([]);
  const [sort,           setSort]           = useState('newest');
  const [favs,           setFavs]           = useState([2, 5]);
  const [showFavsOnly,   setShowFavsOnly]   = useState(false);
  const [visibleCount,   setVisibleCount]   = useState(PAGE_SIZE);

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [query, selectedTags, selectedTopics, sort, showFavsOnly]);

  const filtered = useMemo(() => {
    let items = ARTICLES;

    if (selectedTags.length > 0) {
      items = items.filter((i) => selectedTags.includes(i.tag));
    }

    if (selectedTopics.length > 0) {
      items = items.filter((i) => selectedTopics.includes(i.topic));
    }

    if (query.trim()) {
      const q = query.trim().toLowerCase();
      items = items.filter(
        (i) =>
          i.title.toLowerCase().includes(q) ||
          i.description.toLowerCase().includes(q) ||
          i.topic.toLowerCase().includes(q),
      );
    }

    if (showFavsOnly) {
      items = items.filter((i) => favs.includes(i.id));
    }

    return sort === 'oldest' ? [...items].reverse() : items;
  }, [query, selectedTags, selectedTopics, sort, showFavsOnly, favs]);

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visibleCount < filtered.length;

  function loadMore() {
    setVisibleCount((c) => c + PAGE_SIZE);
  }

  function toggleFav(id, e) {
    e?.stopPropagation();
    setFavs((prev) => (prev.includes(id) ? prev.filter((f) => f !== id) : [...prev, id]));
  }

  return {
    setQuery,
    selectedTags,   setSelectedTags,
    selectedTopics, setSelectedTopics,
    sort, setSort,
    favs, toggleFav,
    showFavsOnly, setShowFavsOnly,
    visible, hasMore, loadMore,
  };
}
