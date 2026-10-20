import { render, screen, fireEvent } from '@testing-library/react';
import EditableAttachmentList from './EditableAttachmentList';

const att1 = {
  uuid: 'att-1',
  originalFilename: 'отчёт.pdf',
  mimeType: 'application/pdf',
  fileSize: 153600,
  isImage: false,
};

const att2 = {
  uuid: 'att-2',
  originalFilename: 'фото.jpg',
  mimeType: 'image/jpeg',
  fileSize: 512 * 1024,
  isImage: true,
};

// ── renders ──────────────────────────────────────────────────────────────────

test('renders list with filenames', () => {
  render(<EditableAttachmentList attachments={[att1, att2]} />);
  expect(screen.getByText('отчёт.pdf')).toBeInTheDocument();
  expect(screen.getByText('фото.jpg')).toBeInTheDocument();
});

test('returns null when attachments is empty', () => {
  const { container } = render(<EditableAttachmentList attachments={[]} />);
  expect(container).toBeEmptyDOMElement();
});

test('returns null when all attachments are in removedUuids', () => {
  const { container } = render(
    <EditableAttachmentList
      attachments={[att1]}
      removedUuids={['att-1']}
    />,
  );
  expect(container).toBeEmptyDOMElement();
});

// ── remove button ─────────────────────────────────────────────────────────────

test('remove button has accessible aria-label', () => {
  render(<EditableAttachmentList attachments={[att1]} />);
  expect(screen.getByRole('button', { name: 'Убрать отчёт.pdf' })).toBeInTheDocument();
});

test('clicking remove calls onRemove with attachment uuid', () => {
  const onRemove = jest.fn();
  render(<EditableAttachmentList attachments={[att1]} onRemove={onRemove} />);
  fireEvent.click(screen.getByRole('button', { name: 'Убрать отчёт.pdf' }));
  expect(onRemove).toHaveBeenCalledWith('att-1');
});

test('remove button is disabled when disabled=true', () => {
  const onRemove = jest.fn();
  render(<EditableAttachmentList attachments={[att1]} onRemove={onRemove} disabled />);
  const btn = screen.getByRole('button', { name: 'Убрать отчёт.pdf' });
  expect(btn).toBeDisabled();
  fireEvent.click(btn);
  expect(onRemove).not.toHaveBeenCalled();
});

test('remove button is disabled when no onRemove provided', () => {
  render(<EditableAttachmentList attachments={[att1]} />);
  expect(screen.getByRole('button', { name: 'Убрать отчёт.pdf' })).toBeDisabled();
});

// ── removedUuids filtering ────────────────────────────────────────────────────

test('hides attachment whose uuid is in removedUuids', () => {
  render(
    <EditableAttachmentList
      attachments={[att1, att2]}
      removedUuids={['att-1']}
    />,
  );
  expect(screen.queryByText('отчёт.pdf')).not.toBeInTheDocument();
  expect(screen.getByText('фото.jpg')).toBeInTheDocument();
});

// ── size display ──────────────────────────────────────────────────────────────

test('renders file size', () => {
  render(<EditableAttachmentList attachments={[att1]} />);
  expect(screen.getByText('150.0 KB')).toBeInTheDocument();
});

// ── fallback filename ─────────────────────────────────────────────────────────

test('shows fallback "Файл" when originalFilename is null', () => {
  const minimal = { uuid: 'x', originalFilename: null, fileSize: null, isImage: false };
  render(<EditableAttachmentList attachments={[minimal]} onRemove={jest.fn()} />);
  expect(screen.getByText('Файл')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Убрать Файл' })).toBeInTheDocument();
});
