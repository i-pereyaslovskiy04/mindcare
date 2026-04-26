const API_BASE_URL = process.env.REACT_APP_API_URL || '/api';

const JSON_HEADERS = { 'Content-Type': 'application/json' };

const handleResponse = async (response) => {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || body.message || `HTTP ${response.status}`);
  }
  return response.json();
};

// All mutation functions accept a single object parameter for consistency.
// GET functions take plain primitive arguments.

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

export const getNews = async (page = 1, limit = 10) => {
  const res = await fetch(`${API_BASE_URL}/news?page=${page}&limit=${limit}`);
  return handleResponse(res);
};

export const getNewsById = async (id) => {
  const res = await fetch(`${API_BASE_URL}/news/${id}`);
  return handleResponse(res);
};

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
