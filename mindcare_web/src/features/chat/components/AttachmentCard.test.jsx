import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import AttachmentCard, { formatFileSize } from './AttachmentCard';

// Мок browser download API (jsdom не поддерживает createObjectURL/revokeObjectURL).
beforeAll(() => {
  global.URL.createObjectURL = jest.fn(() => 'blob:test-url');
  global.URL.revokeObjectURL = jest.fn();
});

afterEach(() => {
  jest.clearAllMocks();
});

// ── formatFileSize ────────────────────────────────────────────────────────────

describe('formatFileSize', () => {
  test('returns empty string for null/undefined', () => {
    expect(formatFileSize(null)).toBe('');
    expect(formatFileSize(undefined)).toBe('');
  });

  test('formats bytes as B', () => {
    expect(formatFileSize(0)).toBe('0 B');
    expect(formatFileSize(512)).toBe('512 B');
    expect(formatFileSize(1023)).toBe('1023 B');
  });

  test('formats kilobytes as KB', () => {
    expect(formatFileSize(1024)).toBe('1.0 KB');
    expect(formatFileSize(2048)).toBe('2.0 KB');
    expect(formatFileSize(1536)).toBe('1.5 KB');
  });

  test('formats megabytes as MB', () => {
    expect(formatFileSize(1024 * 1024)).toBe('1.0 MB');
    expect(formatFileSize(2.5 * 1024 * 1024)).toBe('2.5 MB');
  });
});

// ── download trigger (через компонент) ───────────────────────────────────────

test('download trigger: createObjectURL called with blob, revokeObjectURL called after', async () => {
  const blob = new Blob(['pdf'], { type: 'application/pdf' });
  const onDownload = jest.fn().mockResolvedValue({ blob, filename: 'отчёт.pdf' });
  const clickSpy = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

  render(<AttachmentCard attachment={docAtt} onDownload={onDownload} />);
  fireEvent.click(screen.getByRole('button', { name: /Скачать/ }));

  await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalledWith(blob));
  await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalled());
  clickSpy.mockRestore();
});

// ── AttachmentCard ────────────────────────────────────────────────────────────

const docAtt = {
  uuid: 'att-1',
  originalFilename: 'отчёт.pdf',
  mimeType: 'application/pdf',
  fileSize: 153600,
  isImage: false,
  createdAt: '2024-01-01T10:00:00.000Z',
};

const imageAtt = {
  uuid: 'att-2',
  originalFilename: 'фото.jpg',
  mimeType: 'image/jpeg',
  fileSize: 512 * 1024,
  isImage: true,
  createdAt: '2024-01-01T10:00:00.000Z',
};

test('renders filename', () => {
  render(<AttachmentCard attachment={docAtt} onDownload={jest.fn()} />);
  expect(screen.getByText('отчёт.pdf')).toBeInTheDocument();
});

test('renders formatted file size', () => {
  render(<AttachmentCard attachment={docAtt} onDownload={jest.fn()} />);
  expect(screen.getByText('150.0 KB')).toBeInTheDocument();
});

test('download button has accessible aria-label', () => {
  render(<AttachmentCard attachment={docAtt} onDownload={jest.fn()} />);
  expect(screen.getByRole('button', { name: /Скачать отчёт\.pdf/ })).toBeInTheDocument();
});

test('clicking download calls onDownload with the attachment', async () => {
  const blob = new Blob(['pdf'], { type: 'application/pdf' });
  const onDownload = jest.fn().mockResolvedValue({ blob, filename: 'отчёт.pdf' });
  const clickSpy = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

  render(<AttachmentCard attachment={docAtt} onDownload={onDownload} />);
  fireEvent.click(screen.getByRole('button', { name: /Скачать/ }));

  await waitFor(() => expect(onDownload).toHaveBeenCalledWith(docAtt));
  clickSpy.mockRestore();
});

test('button is disabled and download not called when disabled=true', () => {
  const onDownload = jest.fn();
  render(<AttachmentCard attachment={docAtt} onDownload={onDownload} disabled />);
  const btn = screen.getByRole('button', { name: /Скачать/ });
  expect(btn).toBeDisabled();
  fireEvent.click(btn);
  expect(onDownload).not.toHaveBeenCalled();
});

test('button is disabled when no onDownload provided', () => {
  render(<AttachmentCard attachment={docAtt} />);
  const btn = screen.getByRole('button');
  expect(btn).toBeDisabled();
});

test('shows loading state (aria-label changes, button disabled) during download', async () => {
  let resolveDownload;
  const onDownload = jest.fn(
    () => new Promise((res) => { resolveDownload = res; }),
  );

  render(<AttachmentCard attachment={docAtt} onDownload={onDownload} />);
  fireEvent.click(screen.getByRole('button', { name: /Скачать/ }));

  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Загрузка…' })).toBeDisabled(),
  );

  await act(async () => {
    resolveDownload({ blob: new Blob(), filename: null });
  });

  await waitFor(() =>
    expect(screen.getByRole('button', { name: /Скачать/ })).not.toBeDisabled(),
  );
});

test('shows error message when download fails', async () => {
  const onDownload = jest.fn().mockRejectedValue(new Error('Network error'));
  render(<AttachmentCard attachment={docAtt} onDownload={onDownload} />);
  fireEvent.click(screen.getByRole('button', { name: /Скачать/ }));
  expect(await screen.findByText('Не удалось скачать файл.')).toBeInTheDocument();
});

test('long filename is truncated by CSS (title attribute set)', () => {
  const longAtt = { ...docAtt, originalFilename: 'очень-длинное-имя-файла-которое-не-помещается.pdf' };
  render(<AttachmentCard attachment={longAtt} onDownload={jest.fn()} />);
  const nameEl = screen.getByTitle('очень-длинное-имя-файла-которое-не-помещается.pdf');
  expect(nameEl).toBeInTheDocument();
});

test('image attachment: renders filename and download button, no inline <img> preview', () => {
  render(<AttachmentCard attachment={imageAtt} onDownload={jest.fn()} />);
  expect(screen.getByText('фото.jpg')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Скачать фото\.jpg/ })).toBeInTheDocument();
  // Нет тега <img> — только SVG-иконки, роль 'img' не назначена
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
});

test('attachment with missing fields does not crash', () => {
  const minimal = { uuid: 'x', originalFilename: null, fileSize: null, isImage: false };
  render(<AttachmentCard attachment={minimal} onDownload={jest.fn()} />);
  // Показывает fallback "Файл"
  expect(screen.getByText('Файл')).toBeInTheDocument();
});

// Stage 32d-hotfix: outgoing variant — filename и кнопка скачивания доступны.
test('outgoing prop: renders filename and download button in outgoing context', () => {
  render(<AttachmentCard attachment={docAtt} onDownload={jest.fn()} outgoing />);
  expect(screen.getByText('отчёт.pdf')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Скачать отчёт\.pdf/ })).toBeInTheDocument();
});
