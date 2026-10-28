import { useAuth } from '../../../features/auth/AuthContext';
import MaterialsLibrary from '../../../features/materials/ui/MaterialsLibrary';
import styles from './MaterialsPage.module.css';

const studentMaterialPath = (id) => `/student/materials/${id}`;

export default function MaterialsPage() {
  const { isImpersonating } = useAuth();
  return (
    <div className={styles.page}>
      <div className={styles.labelTag}>Библиотека</div>
      <h1 className={styles.pageTitle}>
        Материалы <em>и статьи</em>
      </h1>
      <p className={styles.pageSub}>
        Опубликованные материалы психологической службы: статьи, практики и упражнения.
        Сохраняйте важное в избранное — отметки доступны на любом устройстве.
      </p>

      <MaterialsLibrary variant="compact" withFavorites={!isImpersonating} getItemPath={studentMaterialPath} />
    </div>
  );
}
