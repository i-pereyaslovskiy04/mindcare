import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AttachmentList from './AttachmentList';

// Мок browser download API.
beforeAll(() => {
  global.URL.createObjectURL = jest.fn(() => 'blob:test');
  global.URL.revokeObjectURL = jest.fn();
});

afterEach(() => {
  jest.clearAllMocks();
});

const att1 = {
  uuid: 'a1',
  originalFilename: 'документ.pdf',
  mimeType: 'application/pdf',
  fileSize: 1024,
  isImage: false,
};
const att2 = {
  uuid: 'a2',
  originalFilename: 'фото.png',
  mimeType: 'image/png',
  fileSize: 2048,
  isImage: true,
};

test('returns null for empty attachments array', () => {
  const { container } = render(
    <AttachmentList attachments={[]} onDownloadAttachment={jest.fn()} />,
  );
  expect(container).toBeEmptyDOMElement();
});

test('returns null when attachments is undefined', () => {
  const { container } = render(<AttachmentList onDownloadAttachment={jest.fn()} />);
  expect(container).toBeEmptyDOMElement();
});

test('renders one card for a single attachment', () => {
  render(<AttachmentList attachments={[att1]} onDownloadAttachment={jest.fn()} />);
  expect(screen.getByText('документ.pdf')).toBeInTheDocument();
});

test('renders a card for each attachment in the list', () => {
  render(
    <AttachmentList attachments={[att1, att2]} onDownloadAttachment={jest.fn()} />,
  );
  expect(screen.getByText('документ.pdf')).toBeInTheDocument();
  expect(screen.getByText('фото.png')).toBeInTheDocument();
});

test('passes onDownloadAttachment to each card as onDownload', async () => {
  const blob = new Blob(['data']);
  const onDownload = jest.fn().mockResolvedValue({ blob, filename: 'документ.pdf' });
  const clickSpy = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

  render(
    <AttachmentList attachments={[att1]} onDownloadAttachment={onDownload} />,
  );
  fireEvent.click(screen.getByRole('button', { name: /Скачать документ\.pdf/ }));
  await waitFor(() => expect(onDownload).toHaveBeenCalledWith(att1));
  clickSpy.mockRestore();
});

test('cards are disabled when onDownloadAttachment is null', () => {
  render(<AttachmentList attachments={[att1, att2]} onDownloadAttachment={null} />);
  const buttons = screen.getAllByRole('button');
  buttons.forEach((btn) => expect(btn).toBeDisabled());
});
