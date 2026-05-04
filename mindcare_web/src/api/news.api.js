import { MOCK_NEWS } from '../data/news.mock';

const API_BASE = process.env.REACT_APP_API_URL || '/api';

async function _handleResponse(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.message || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function getNews(page = 1, limit = 10) {
  try {
    const res = await fetch(`${API_BASE}/news?page=${page}&limit=${limit}`);
    return await _handleResponse(res);
  } catch {
    const start = (page - 1) * limit;
    return {
      items: MOCK_NEWS.slice(start, start + limit),
      total: MOCK_NEWS.length,
    };
  }
}

export async function getNewsById(id) {
  try {
    const res = await fetch(`${API_BASE}/news/${id}`);
    return await _handleResponse(res);
  } catch {
    const found = MOCK_NEWS.find((item) => item.id === Number(id));
    if (!found) throw new Error('Not found');
    return found;
  }
}
