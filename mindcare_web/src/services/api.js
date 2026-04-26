const API_BASE_URL = process.env.REACT_APP_API_URL || '/api';

const JSON_HEADERS = { 'Content-Type': 'application/json' };

const handleResponse = async (response) => {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || body.message || `HTTP ${response.status}`);
  }
  return response.json();
};

// Fallback data used when the backend is unavailable.
// To switch to real API: remove the try/catch wrappers in getNews and getNewsById.
const MOCK_NEWS = [
  { id: 1,  tag: 'Мероприятия', title: 'Открытый день психологической службы ДонГУ',    description: 'Приглашаем познакомиться с командой и узнать о доступных программах поддержки.',           date: '18 апреля 2025' },
  { id: 2,  tag: 'Статья',      title: 'Как справляться с учебным стрессом',              description: 'Практические советы для студентов: от тайм-менеджмента до техник дыхания.',                date: '14 апреля 2025' },
  { id: 3,  tag: 'Вебинар',     title: 'Тревожность: практика осознанности',              description: 'Онлайн-встреча с психологом центра о методах снижения фоновой тревоги.',                    date: '9 апреля 2025'  },
  { id: 4,  tag: 'Мероприятия', title: 'Групповая терапия: открыт новый поток записи',   description: 'Запись на сессии по работе с тревогой и межличностными отношениями.',                      date: '7 апреля 2025'  },
  { id: 5,  tag: 'Статья',      title: 'Обновлены тесты самодиагностики',                 description: 'Новые инструменты для оценки эмоционального состояния и уровня стресса.',                  date: '2 апреля 2025'  },
  { id: 6,  tag: 'Новости',     title: 'В команду центра пришёл новый специалист',        description: 'Клинический психолог с опытом работы с молодёжью и кризисными состояниями.',               date: '28 марта 2025'  },
  { id: 7,  tag: 'Статья',      title: 'Эмоциональное выгорание: как распознать и что делать', description: 'Признаки выгорания у студентов и первые шаги к восстановлению.',                  date: '22 марта 2025'  },
  { id: 8,  tag: 'Мероприятия', title: 'Мастер-класс «Здоровый сон и продуктивность»',   description: 'Разберём связь качества сна с успеваемостью и эмоциональным фоном.',                      date: '17 марта 2025'  },
  { id: 9,  tag: 'Новости',     title: 'Запущена горячая линия психологической помощи',   description: 'Студенты теперь могут получить поддержку в любое время суток.',                           date: '10 марта 2025'  },
  { id: 10, tag: 'Статья',      title: 'Введение в когнитивно-поведенческую терапию',     description: 'Что такое КПТ, как она работает и кому подходит.',                                         date: '3 марта 2025'   },
  { id: 11, tag: 'Мероприятия', title: 'Открыт клуб медитации для студентов',             description: 'Еженедельные практики осознанности в кампусе — вход свободный.',                          date: '24 февраля 2025' },
  { id: 12, tag: 'Новости',     title: 'Программа равной поддержки: набор волонтёров',    description: 'Присоединяйтесь к команде студентов, которые помогают своим однокурсникам.',              date: '18 февраля 2025' },
];

// ─── Auth ────────────────────────────────────────────────────────────────────

export const login = async ({ email, password }) => {
  const res = await fetch(`${API_BASE_URL}/login`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, password }),
  });
  return handleResponse(res);
};

export const register = async ({ name, email, password }) => {
  const res = await fetch(`${API_BASE_URL}/register`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ name, email, password }),
  });
  return handleResponse(res);
};

export const getProfile = async () => {
  const res = await fetch(`${API_BASE_URL}/profile`);
  return handleResponse(res);
};

export const logout = async () => {
  const res = await fetch(`${API_BASE_URL}/logout`, {
    method: 'POST',
    headers: JSON_HEADERS,
  });
  return handleResponse(res);
};

export const forgotPassword = async ({ email }) => {
  const res = await fetch(`${API_BASE_URL}/forgot-password`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ email }),
  });
  return handleResponse(res);
};

export const resetPassword = async ({ token, newPassword }) => {
  const res = await fetch(`${API_BASE_URL}/reset-password`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  return handleResponse(res);
};

// ─── News ─────────────────────────────────────────────────────────────────────
// Both functions silently fall back to MOCK_NEWS when the backend is unreachable.
// When the real API is ready, simply remove the try/catch wrappers.

export const getNews = async (page = 1, limit = 10) => {
  try {
    const res = await fetch(`${API_BASE_URL}/news?page=${page}&limit=${limit}`);
    return await handleResponse(res);
  } catch (_e) {
    const start = (page - 1) * limit;
    return {
      items: MOCK_NEWS.slice(start, start + limit),
      total: MOCK_NEWS.length,
    };
  }
};

export const getNewsById = async (id) => {
  try {
    const res = await fetch(`${API_BASE_URL}/news/${id}`);
    return await handleResponse(res);
  } catch (_e) {
    const found = MOCK_NEWS.find((item) => item.id === Number(id));
    if (!found) throw new Error('Not found');
    return found;
  }
};

// ─── Appointments / Psychologists ─────────────────────────────────────────────

export const bookAppointment = async (data) => {
  const res = await fetch(`${API_BASE_URL}/appointments`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
  return handleResponse(res);
};

export const getAvailableSlots = async (psychologistId, date) => {
  const res = await fetch(
    `${API_BASE_URL}/psychologists/${psychologistId}/available-slots?date=${date}`
  );
  return handleResponse(res);
};

export const getPsychologists = async () => {
  const res = await fetch(`${API_BASE_URL}/psychologists`);
  return handleResponse(res);
};
