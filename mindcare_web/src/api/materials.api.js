import { MOCK_MATERIALS } from '../data/materials.mock';

const API_BASE = process.env.REACT_APP_API_URL || '/api';

async function _handleResponse(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function getMaterials() {
  try {
    const res = await fetch(`${API_BASE}/materials`);
    return await _handleResponse(res);
  } catch {
    return MOCK_MATERIALS;
  }
}

export async function getMaterialById(id) {
  try {
    const res = await fetch(`${API_BASE}/materials/${id}`);
    return await _handleResponse(res);
  } catch {
    const found = MOCK_MATERIALS.find((m) => m.id === id);
    if (!found) throw new Error('Not found');
    return found;
  }
}
