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
