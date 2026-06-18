import { render, screen, fireEvent } from '@testing-library/react';
import ImageLightbox from './ImageLightbox';

const att = {
  uuid: 'att-img',
  originalFilename: 'фото.jpg',
  mimeType: 'image/jpeg',
  fileSize: 102400,
  isImage: true,
};

const defaultProps = {
  attachment: att,
  objectUrl: null,
  loading: false,
  error: null,
  onClose: jest.fn(),
};

afterEach(() => jest.clearAllMocks());

// ── rendering ─────────────────────────────────────────────────────────────────

test('renders dialog with accessible role and aria-modal', () => {
  render(<ImageLightbox {...defaultProps} />);
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true');
});

test('renders loading state', () => {
  render(<ImageLightbox {...defaultProps} loading />);
  expect(screen.getByTestId('lightbox-loading')).toBeInTheDocument();
  expect(screen.getByTestId('lightbox-loading')).toHaveAttribute('role', 'status');
});

test('does not render image while loading', () => {
  render(<ImageLightbox {...defaultProps} loading objectUrl="blob:test" />);
  expect(screen.queryByTestId('lightbox-image')).not.toBeInTheDocument();
});

test('renders error state', () => {
  render(<ImageLightbox {...defaultProps} error="Не удалось загрузить изображение." />);
  expect(screen.getByTestId('lightbox-error')).toBeInTheDocument();
  expect(screen.getByText('Не удалось загрузить изображение.')).toBeInTheDocument();
  expect(screen.getByTestId('lightbox-error')).toHaveAttribute('role', 'alert');
});

test('does not render image when error is set', () => {
  render(
    <ImageLightbox {...defaultProps} objectUrl="blob:test" error="ошибка" />,
  );
  expect(screen.queryByTestId('lightbox-image')).not.toBeInTheDocument();
});

test('renders image when objectUrl provided and no error/loading', () => {
  render(<ImageLightbox {...defaultProps} objectUrl="blob:test-url" />);
  const img = screen.getByTestId('lightbox-image');
  expect(img).toBeInTheDocument();
  expect(img).toHaveAttribute('src', 'blob:test-url');
  expect(img).toHaveAttribute('alt', 'фото.jpg');
});

test('renders close button with accessible label', () => {
  render(<ImageLightbox {...defaultProps} />);
  expect(screen.getByRole('button', { name: 'Закрыть просмотр' })).toBeInTheDocument();
});

// ── close behaviour ───────────────────────────────────────────────────────────

test('calls onClose when close button is clicked', () => {
  const onClose = jest.fn();
  render(<ImageLightbox {...defaultProps} onClose={onClose} />);
  fireEvent.click(screen.getByRole('button', { name: 'Закрыть просмотр' }));
  expect(onClose).toHaveBeenCalledTimes(1);
});

test('calls onClose when overlay (backdrop) is clicked', () => {
  const onClose = jest.fn();
  render(<ImageLightbox {...defaultProps} onClose={onClose} />);
  fireEvent.click(screen.getByTestId('lightbox-overlay'));
  expect(onClose).toHaveBeenCalledTimes(1);
});

test('does NOT call onClose when image content area is clicked', () => {
  const onClose = jest.fn();
  render(<ImageLightbox {...defaultProps} onClose={onClose} objectUrl="blob:test" />);
  fireEvent.click(screen.getByTestId('lightbox-content'));
  expect(onClose).not.toHaveBeenCalled();
});

test('does NOT call onClose when image itself is clicked', () => {
  const onClose = jest.fn();
  render(<ImageLightbox {...defaultProps} onClose={onClose} objectUrl="blob:test" />);
  fireEvent.click(screen.getByTestId('lightbox-image'));
  expect(onClose).not.toHaveBeenCalled();
});

test('calls onClose when Escape key is pressed', () => {
  const onClose = jest.fn();
  render(<ImageLightbox {...defaultProps} onClose={onClose} />);
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(onClose).toHaveBeenCalledTimes(1);
});

test('does NOT call onClose for non-Escape key', () => {
  const onClose = jest.fn();
  render(<ImageLightbox {...defaultProps} onClose={onClose} />);
  fireEvent.keyDown(document, { key: 'Enter' });
  expect(onClose).not.toHaveBeenCalled();
});

test('removes keydown listener on unmount', () => {
  const onClose = jest.fn();
  const { unmount } = render(<ImageLightbox {...defaultProps} onClose={onClose} />);
  unmount();
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(onClose).not.toHaveBeenCalled();
});

// ── filename fallback ─────────────────────────────────────────────────────────

test('uses "Изображение" as alt and aria-label when filename is null', () => {
  const noName = { ...att, originalFilename: null };
  render(<ImageLightbox {...defaultProps} attachment={noName} objectUrl="blob:x" />);
  expect(screen.getByAltText('Изображение')).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toHaveAttribute(
    'aria-label',
    'Просмотр изображения: Изображение',
  );
});
