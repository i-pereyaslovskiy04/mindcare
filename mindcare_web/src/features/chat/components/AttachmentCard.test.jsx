import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import AttachmentCard, { formatFileSize } from './AttachmentCard';
import { saveBlobToDisk } from '../../../api/client';

// Мокируем saveBlobToDisk (тестируется отдельно в client.test.js).
jest.mock('../../../api/client', () => ({
  saveBlobToDisk: jest.fn(),
}));

beforeEach(() => {
  // Реализация по умолчанию: вызывает fetchFn, чтобы onDownload тоже вызывался.
  // Устанавливается в beforeEach (не в afterEach) — jest.restoreAllMocks/clearAllMocks
  // может сбрасывать реализации standalone jest.fn() в некоторых версиях jest.
  saveBlobToDisk.mockImplementation(async (fn) => { await fn(); });
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

// ── download trigger ──────────────────────────────────────────────────────────

test('download trigger: saveBlobToDisk called with fetchFn and display filename', async () => {
  const blob = new Blob(['pdf'], { type: 'application/pdf' });
  const onDownload = jest.fn().mockResolvedValue({ blob, filename: 'отчёт.pdf' });

  render(<AttachmentCard attachment={docAtt} onDownload={onDownload} />);
  fireEvent.click(screen.getByRole('button', { name: /Скачать/ }));

  await waitFor(() => expect(saveBlobToDisk).toHaveBeenCalled());
  expect(saveBlobToDisk).toHaveBeenCalledWith(
    expect.any(Function),
    docAtt.originalFilename,
  );
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

  render(<AttachmentCard attachment={docAtt} onDownload={onDownload} />);
  fireEvent.click(screen.getByRole('button', { name: /Скачать/ }));

  await waitFor(() => expect(onDownload).toHaveBeenCalledWith(docAtt));
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

test('outgoing prop: renders filename and download button in outgoing context', () => {
  render(<AttachmentCard attachment={docAtt} onDownload={jest.fn()} outgoing />);
  expect(screen.getByText('отчёт.pdf')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Скачать отчёт\.pdf/ })).toBeInTheDocument();
});

// ── download safety (Stage 32d-hotfix-b) ─────────────────────────────────────

test('download button has type=button (prevents form submit)', () => {
  render(<AttachmentCard attachment={docAtt} onDownload={jest.fn()} />);
  expect(screen.getByRole('button', { name: /Скачать/ })).toHaveAttribute('type', 'button');
});

test('download click calls preventDefault', () => {
  const onDownload = jest.fn().mockResolvedValue({ blob: new Blob(), filename: null });
  render(<AttachmentCard attachment={docAtt} onDownload={onDownload} />);
  const result = fireEvent.click(screen.getByRole('button', { name: /Скачать/ }));
  // fireEvent returns false when preventDefault was called
  expect(result).toBe(false);
});

test('download click stops propagation to parent', () => {
  const parentSpy = jest.fn();
  const onDownload = jest.fn().mockResolvedValue({ blob: new Blob(), filename: null });
  render(
    <div role="presentation" onClick={parentSpy}>
      <AttachmentCard attachment={docAtt} onDownload={onDownload} />
    </div>,
  );
  fireEvent.click(screen.getByRole('button', { name: /Скачать/ }));
  expect(parentSpy).not.toHaveBeenCalled();
});

// ── image preview (Stage 32i) ─────────────────────────────────────────────────

const svgAtt = {
  uuid: 'att-svg',
  originalFilename: 'icon.svg',
  mimeType: 'image/svg+xml',
  fileSize: 1024,
  isImage: false,
  createdAt: '2024-01-01T10:00:00.000Z',
};

describe('image preview button visibility', () => {
  test('image attachment shows preview button', () => {
    render(<AttachmentCard attachment={imageAtt} onDownload={jest.fn()} />);
    expect(screen.getByTestId('preview-btn')).toBeInTheDocument();
  });

  test('non-image (PDF) attachment does not show preview button', () => {
    render(<AttachmentCard attachment={docAtt} onDownload={jest.fn()} />);
    expect(screen.queryByTestId('preview-btn')).not.toBeInTheDocument();
  });

  test('SVG (mimeType image/svg+xml, isImage=false) does not show preview button', () => {
    render(<AttachmentCard attachment={svgAtt} onDownload={jest.fn()} />);
    expect(screen.queryByTestId('preview-btn')).not.toBeInTheDocument();
  });

  test('image without onDownload does not show preview button', () => {
    render(<AttachmentCard attachment={imageAtt} />);
    expect(screen.queryByTestId('preview-btn')).not.toBeInTheDocument();
  });

  test('preview button has type=button', () => {
    render(<AttachmentCard attachment={imageAtt} onDownload={jest.fn()} />);
    expect(screen.getByTestId('preview-btn')).toHaveAttribute('type', 'button');
  });
});

describe('image preview interaction', () => {
  beforeEach(() => {
    global.URL.createObjectURL = jest.fn(() => 'blob:preview-url');
    global.URL.revokeObjectURL = jest.fn();
  });

  test('preview click calls onDownload, not saveBlobToDisk', async () => {
    const onDownload = jest.fn().mockResolvedValue({ blob: new Blob(['img'], { type: 'image/jpeg' }), filename: 'фото.jpg' });
    render(<AttachmentCard attachment={imageAtt} onDownload={onDownload} />);
    fireEvent.click(screen.getByTestId('preview-btn'));
    await waitFor(() => expect(onDownload).toHaveBeenCalledWith(imageAtt));
    expect(saveBlobToDisk).not.toHaveBeenCalled();
  });

  test('preview click opens lightbox dialog', async () => {
    const onDownload = jest.fn().mockResolvedValue({ blob: new Blob(['img']), filename: 'фото.jpg' });
    render(<AttachmentCard attachment={imageAtt} onDownload={onDownload} />);
    fireEvent.click(screen.getByTestId('preview-btn'));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  test('creates object URL after successful fetch', async () => {
    const blob = new Blob(['img'], { type: 'image/jpeg' });
    const onDownload = jest.fn().mockResolvedValue({ blob, filename: 'фото.jpg' });
    render(<AttachmentCard attachment={imageAtt} onDownload={onDownload} />);
    fireEvent.click(screen.getByTestId('preview-btn'));
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalledWith(blob));
  });

  test('shows error when fetch fails', async () => {
    const onDownload = jest.fn().mockRejectedValue(new Error('Network error'));
    render(<AttachmentCard attachment={imageAtt} onDownload={onDownload} />);
    fireEvent.click(screen.getByTestId('preview-btn'));
    expect(await screen.findByText('Не удалось загрузить изображение.')).toBeInTheDocument();
  });

  test('preview click stops propagation to parent', () => {
    const parentSpy = jest.fn();
    const onDownload = jest.fn().mockResolvedValue({ blob: new Blob(), filename: null });
    render(
      <div role="presentation" onClick={parentSpy}>
        <AttachmentCard attachment={imageAtt} onDownload={onDownload} />
      </div>,
    );
    fireEvent.click(screen.getByTestId('preview-btn'));
    expect(parentSpy).not.toHaveBeenCalled();
  });

  test('download button still works when preview is not open', async () => {
    const onDownload = jest.fn().mockResolvedValue({ blob: new Blob(), filename: 'фото.jpg' });
    render(<AttachmentCard attachment={imageAtt} onDownload={onDownload} />);
    fireEvent.click(screen.getByRole('button', { name: /Скачать фото\.jpg/ }));
    await waitFor(() => expect(saveBlobToDisk).toHaveBeenCalled());
  });

  test('revokes object URL when lightbox is closed', async () => {
    const onDownload = jest.fn().mockResolvedValue({ blob: new Blob(['img']), filename: 'фото.jpg' });
    render(<AttachmentCard attachment={imageAtt} onDownload={onDownload} />);
    fireEvent.click(screen.getByTestId('preview-btn'));
    await screen.findByRole('dialog');
    fireEvent.click(screen.getByTestId('lightbox-close'));
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview-url'));
  });

  test('revokes object URL on unmount while lightbox is open', async () => {
    const onDownload = jest.fn().mockResolvedValue({ blob: new Blob(['img']), filename: 'фото.jpg' });
    const { unmount } = render(<AttachmentCard attachment={imageAtt} onDownload={onDownload} />);
    fireEvent.click(screen.getByTestId('preview-btn'));
    // Wait for the blob fetch to complete and URL to be created before unmounting.
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview-url');
  });
});

// ── saveBlobToDisk integration — AbortError handling (Stage 32d-hotfix-b) ─────

describe('save dialog cancel handling', () => {
  test('AbortError from saveBlobToDisk does not show error message', async () => {
    saveBlobToDisk.mockRejectedValueOnce(new DOMException('Cancelled by user', 'AbortError'));

    render(<AttachmentCard attachment={docAtt} onDownload={jest.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /Скачать/ }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Скачать/ })).not.toBeDisabled(),
    );
    expect(screen.queryByText('Не удалось скачать файл.')).not.toBeInTheDocument();
  });

  test('non-AbortError shows error message', async () => {
    saveBlobToDisk.mockRejectedValueOnce(new Error('Write failed'));

    render(<AttachmentCard attachment={docAtt} onDownload={jest.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /Скачать/ }));

    expect(await screen.findByText('Не удалось скачать файл.')).toBeInTheDocument();
  });
});
