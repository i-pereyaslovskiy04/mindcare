import { useRef, useState } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Image from '@tiptap/extension-image';
import { uploadImage } from '../../../api/media.api';
import styles from './TiptapEditor.module.css';

const HEADINGS = [1, 2, 3];

const TOOLBAR = [
  { action: 'toggleBold',        isActive: 'bold',        label: 'Ж',   title: 'Жирный (Ctrl+B)' },
  { action: 'toggleItalic',      isActive: 'italic',      label: 'К',   title: 'Курсив (Ctrl+I)' },
  { action: 'toggleBulletList',  isActive: 'bulletList',  label: '• —', title: 'Маркированный список' },
  { action: 'toggleOrderedList', isActive: 'orderedList', label: '1.',  title: 'Нумерованный список' },
  { action: 'toggleBlockquote',  isActive: 'blockquote',  label: '❝',   title: 'Цитата' },
  { action: 'toggleCodeBlock',   isActive: 'codeBlock',   label: '</>', title: 'Блок кода' },
  { action: 'setHorizontalRule', isActive: null,          label: '—',   title: 'Горизонтальная линия' },
];

export default function TiptapEditor({ value, onChange, placeholder = 'Введите текст...' }) {
  const [imgUploading, setImgUploading] = useState(false);
  const [imgError, setImgError]         = useState('');
  const fileInputRef   = useRef(null);
  // Стабильная ссылка на insertImage — нужна для handlePaste который создаётся
  // один раз при инициализации редактора и не перечитывает closure
  const insertImageRef = useRef(null);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Image.configure({ HTMLAttributes: { class: 'tiptap-image' } }),
    ],
    content: value || '',
    onUpdate({ editor }) {
      onChange(editor.getHTML());
    },
    editorProps: {
      handlePaste(view, event) {
        const items = Array.from(event.clipboardData?.items || []);
        const imageItem = items.find(item => item.type.startsWith('image/'));
        if (!imageItem) return false;
        const file = imageItem.getAsFile();
        if (file) {
          event.preventDefault();
          insertImageRef.current?.(file);
          return true;
        }
        return false;
      },
      // Поддержка drag-and-drop изображений в редактор
      handleDrop(view, event) {
        const files = Array.from(event.dataTransfer?.files || []);
        const imageFile = files.find(f => f.type.startsWith('image/'));
        if (!imageFile) return false;
        event.preventDefault();
        insertImageRef.current?.(imageFile);
        return true;
      },
    },
  });

  // Всегда обновляем ссылку — insertImageRef.current будет содержать
  // актуальную функцию с текущим editor в замыкании
  async function insertImage(file) {
    if (!file || !editor) return;
    setImgUploading(true);
    setImgError('');
    try {
      const result = await uploadImage(file);
      editor.chain().focus().setImage({ src: result.url }).run();
    } catch (err) {
      setImgError(err.message || 'Ошибка загрузки изображения');
    } finally {
      setImgUploading(false);
    }
  }
  insertImageRef.current = insertImage;

  if (!editor) return null;

  const run = (action, args) => {
    const chain = editor.chain().focus();
    if (args !== undefined) chain[action](args).run();
    else chain[action]().run();
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.toolbar} role="toolbar" aria-label="Панель форматирования">
        {HEADINGS.map(level => (
          <button
            key={level}
            type="button"
            title={`Заголовок H${level}`}
            className={`${styles.btn} ${editor.isActive('heading', { level }) ? styles.active : ''}`}
            onMouseDown={e => { e.preventDefault(); run('toggleHeading', { level }); }}
          >
            H{level}
          </button>
        ))}
        <span className={styles.divider} />
        {TOOLBAR.map(({ action, isActive, label, title }) => (
          <button
            key={action}
            type="button"
            title={title}
            className={`${styles.btn} ${isActive && editor.isActive(isActive) ? styles.active : ''}`}
            onMouseDown={e => { e.preventDefault(); run(action); }}
          >
            {label}
          </button>
        ))}
        <span className={styles.divider} />
        <button
          type="button"
          title="Вставить изображение из файла"
          className={`${styles.btn} ${imgUploading ? styles.uploading : ''}`}
          onMouseDown={e => { e.preventDefault(); fileInputRef.current?.click(); }}
          disabled={imgUploading}
        >
          {imgUploading ? '…' : '🖼'}
        </button>
        <span className={styles.divider} />
        <button
          type="button"
          title="Отменить (Ctrl+Z)"
          className={styles.btn}
          onMouseDown={e => { e.preventDefault(); editor.chain().focus().undo().run(); }}
          disabled={!editor.can().undo()}
        >
          ↩
        </button>
        <button
          type="button"
          title="Повторить (Ctrl+Y)"
          className={styles.btn}
          onMouseDown={e => { e.preventDefault(); editor.chain().focus().redo().run(); }}
          disabled={!editor.can().redo()}
        >
          ↪
        </button>
      </div>

      {imgError && (
        <div className={styles.imgError} role="alert">{imgError}</div>
      )}

      <EditorContent editor={editor} className={styles.content} />

      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp"
        className={styles.hiddenInput}
        onChange={e => {
          const file = e.target.files?.[0];
          if (file) insertImage(file);
          e.target.value = '';
        }}
      />
    </div>
  );
}
