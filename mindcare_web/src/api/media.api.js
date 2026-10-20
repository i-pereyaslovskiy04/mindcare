import { apiFetch } from './client';

export async function uploadImage(file) {
  const form = new FormData();
  form.append('file', file);
  return apiFetch('/api/media/upload', {
    method: 'POST',
    body: form,
    // Content-Type не выставляем — браузер сам добавит boundary для multipart
  });
}

// Аудио/видео (для вопросов тестов). Возвращает { uuid, url, file_type, ... }.
export async function uploadMedia(file) {
  const form = new FormData();
  form.append('file', file);
  return apiFetch('/api/media/upload/av', { method: 'POST', body: form });
}
