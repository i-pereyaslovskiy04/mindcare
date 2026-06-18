import { render, screen, fireEvent } from '@testing-library/react';
import AttachmentPreviewLightbox from './AttachmentPreviewLightbox';

// ── shared fixtures ───────────────────────────────────────────────────────────

const imgAtt = {
  uuid: 'att-img',
  originalFilename: 'фото.jpg',
  mimeType: 'image/jpeg',
  fileSize: 102400,
  isImage: true,
};

const pdfAtt = {
  uuid: 'att-pdf',
  originalFilename: 'документ.pdf',
  mimeType: 'application/pdf',
  fileSize: 512000,
  isImage: false,
};

const defaultProps = {
  attachment: imgAtt,
  objectUrl: null,
  loading: false,
  error: null,
  onClose: jest.fn(),
};

afterEach(() => jest.clearAllMocks());

// ── dialog structure ──────────────────────────────────────────────────────────

test('renders dialog with accessible role and aria-modal', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} />);
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true');
});

test('aria-label contains filename', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} />);
  expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'Просмотр: фото.jpg');
});

test('renders close button with accessible label', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} />);
  expect(screen.getByRole('button', { name: 'Закрыть просмотр' })).toBeInTheDocument();
});

// ── loading / error states ────────────────────────────────────────────────────

test('renders loading state', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} loading />);
  expect(screen.getByTestId('lightbox-loading')).toBeInTheDocument();
  expect(screen.getByTestId('lightbox-loading')).toHaveAttribute('role', 'status');
});

test('does not render image while loading', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} loading objectUrl="blob:x" />);
  expect(screen.queryByTestId('lightbox-image')).not.toBeInTheDocument();
  expect(screen.queryByTestId('lightbox-pdf')).not.toBeInTheDocument();
});

test('renders error state', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} error="Не удалось загрузить файл." />);
  expect(screen.getByTestId('lightbox-error')).toBeInTheDocument();
  expect(screen.getByTestId('lightbox-error')).toHaveAttribute('role', 'alert');
});

test('does not render content when error is set', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} objectUrl="blob:x" error="ошибка" />);
  expect(screen.queryByTestId('lightbox-image')).not.toBeInTheDocument();
  expect(screen.queryByTestId('lightbox-pdf')).not.toBeInTheDocument();
});

// ── image mode ────────────────────────────────────────────────────────────────

test('image: renders <img> when objectUrl provided', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} objectUrl="blob:img-url" />);
  const img = screen.getByTestId('lightbox-image');
  expect(img).toBeInTheDocument();
  expect(img).toHaveAttribute('src', 'blob:img-url');
  expect(img).toHaveAttribute('alt', 'фото.jpg');
});

test('image: does not render iframe', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} objectUrl="blob:img-url" />);
  expect(screen.queryByTestId('lightbox-pdf')).not.toBeInTheDocument();
});

test('image: png attachment renders as image', () => {
  const png = { ...imgAtt, mimeType: 'image/png', originalFilename: 'img.png' };
  render(<AttachmentPreviewLightbox {...defaultProps} attachment={png} objectUrl="blob:png" />);
  expect(screen.getByTestId('lightbox-image')).toBeInTheDocument();
});

// ── PDF mode ──────────────────────────────────────────────────────────────────

test('pdf: renders iframe when mimeType is application/pdf', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} attachment={pdfAtt} objectUrl="blob:pdf-url" />);
  const frame = screen.getByTestId('lightbox-pdf');
  expect(frame).toBeInTheDocument();
  expect(frame.tagName).toBe('IFRAME');
});

test('pdf: iframe src is objectUrl', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} attachment={pdfAtt} objectUrl="blob:pdf-url" />);
  expect(screen.getByTestId('lightbox-pdf')).toHaveAttribute('src', 'blob:pdf-url');
});

test('pdf: iframe title is filename', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} attachment={pdfAtt} objectUrl="blob:pdf-url" />);
  expect(screen.getByTestId('lightbox-pdf')).toHaveAttribute('title', 'документ.pdf');
});

test('pdf: does not render <img>', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} attachment={pdfAtt} objectUrl="blob:pdf-url" />);
  expect(screen.queryByTestId('lightbox-image')).not.toBeInTheDocument();
});

test('pdf: does not render iframe while loading', () => {
  render(<AttachmentPreviewLightbox {...defaultProps} attachment={pdfAtt} loading objectUrl="blob:pdf-url" />);
  expect(screen.queryByTestId('lightbox-pdf')).not.toBeInTheDocument();
  expect(screen.getByTestId('lightbox-loading')).toBeInTheDocument();
});

// ── close behaviour ───────────────────────────────────────────────────────────

test('calls onClose when close button is clicked', () => {
  const onClose = jest.fn();
  render(<AttachmentPreviewLightbox {...defaultProps} onClose={onClose} />);
  fireEvent.click(screen.getByRole('button', { name: 'Закрыть просмотр' }));
  expect(onClose).toHaveBeenCalledTimes(1);
});

test('calls onClose when overlay (backdrop) is clicked', () => {
  const onClose = jest.fn();
  render(<AttachmentPreviewLightbox {...defaultProps} onClose={onClose} />);
  fireEvent.click(screen.getByTestId('lightbox-overlay'));
  expect(onClose).toHaveBeenCalledTimes(1);
});

test('does NOT call onClose when content area is clicked', () => {
  const onClose = jest.fn();
  render(<AttachmentPreviewLightbox {...defaultProps} onClose={onClose} objectUrl="blob:x" />);
  fireEvent.click(screen.getByTestId('lightbox-content'));
  expect(onClose).not.toHaveBeenCalled();
});

test('does NOT call onClose when image itself is clicked', () => {
  const onClose = jest.fn();
  render(<AttachmentPreviewLightbox {...defaultProps} onClose={onClose} objectUrl="blob:x" />);
  fireEvent.click(screen.getByTestId('lightbox-image'));
  expect(onClose).not.toHaveBeenCalled();
});

test('calls onClose when Escape key is pressed', () => {
  const onClose = jest.fn();
  render(<AttachmentPreviewLightbox {...defaultProps} onClose={onClose} />);
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(onClose).toHaveBeenCalledTimes(1);
});

test('does NOT call onClose for non-Escape key', () => {
  const onClose = jest.fn();
  render(<AttachmentPreviewLightbox {...defaultProps} onClose={onClose} />);
  fireEvent.keyDown(document, { key: 'Enter' });
  expect(onClose).not.toHaveBeenCalled();
});

test('removes keydown listener on unmount', () => {
  const onClose = jest.fn();
  const { unmount } = render(<AttachmentPreviewLightbox {...defaultProps} onClose={onClose} />);
  unmount();
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(onClose).not.toHaveBeenCalled();
});

// ── filename fallback ─────────────────────────────────────────────────────────

test('uses "Файл" as fallback when originalFilename is null', () => {
  const noName = { ...imgAtt, originalFilename: null };
  render(<AttachmentPreviewLightbox {...defaultProps} attachment={noName} objectUrl="blob:x" />);
  expect(screen.getByAltText('Файл')).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'Просмотр: Файл');
});
