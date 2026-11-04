import {
  createCampaign, deleteCampaignResponse, getCampaignResponses, getCampaigns,
  getPublicCampaign, setCampaignStatus, submitPublicCampaign,
  downloadCampaignResults, getCampaignResults,
} from './campaigns.api';
import { apiFetch, apiFetchBlob } from './client';

jest.mock('./client');

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({});
  apiFetchBlob.mockReset();
});

test('публичная анкета — токен кодируется в пути', () => {
  getPublicCampaign('ab/c');
  expect(apiFetch).toHaveBeenCalledWith('/api/public/campaigns/ab%2Fc');
});

test('отправка — POST с JSON-телом', () => {
  submitPublicCampaign('tok', { answers: [] });
  expect(apiFetch).toHaveBeenCalledWith('/api/public/campaigns/tok/submit', {
    method: 'POST',
    body: JSON.stringify({ answers: [] }),
  });
});

test('список кампаний — keyset before', () => {
  getCampaigns({ size: 10, before: 'u-1' });
  expect(apiFetch).toHaveBeenCalledWith('/api/supervisor/campaigns?size=10&before=u-1');
});

test('создание — только title и test_uuid', () => {
  createCampaign({ title: 'Т', test_uuid: 'u', extra: 1 });
  expect(apiFetch).toHaveBeenCalledWith('/api/supervisor/campaigns', {
    method: 'POST',
    body: JSON.stringify({ title: 'Т', test_uuid: 'u' }),
  });
});

test('статус — PATCH', () => {
  setCampaignStatus('u', 'closed');
  expect(apiFetch).toHaveBeenCalledWith('/api/supervisor/campaigns/u/status', {
    method: 'PATCH',
    body: JSON.stringify({ status: 'closed' }),
  });
});

test('участники — keyset after; удаление ответа — DELETE', () => {
  getCampaignResponses('u', { size: 5, after: 'r-1' });
  expect(apiFetch).toHaveBeenCalledWith('/api/supervisor/campaigns/u/responses?size=5&after=r-1');
  deleteCampaignResponse('u', 'r-1');
  expect(apiFetch).toHaveBeenCalledWith('/api/supervisor/campaigns/u/responses/r-1', {
    method: 'DELETE',
  });
});

test('результаты — только заданные фильтры в query', () => {
  getCampaignResults('u', { faculty_code: 'law', gender: '', type: 'Тип А' });
  expect(apiFetch).toHaveBeenCalledWith(
    '/api/supervisor/campaigns/u/results?faculty_code=law&type=%D0%A2%D0%B8%D0%BF+%D0%90',
  );
  getCampaignResults('u');
  expect(apiFetch).toHaveBeenCalledWith('/api/supervisor/campaigns/u/results');
});

test('выгрузка — blob', () => {
  downloadCampaignResults('u');
  expect(apiFetchBlob).toHaveBeenCalledWith('/api/supervisor/campaigns/u/export.xlsx');
});
