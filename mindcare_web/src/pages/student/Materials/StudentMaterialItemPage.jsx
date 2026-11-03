import { useParams } from 'react-router-dom';
import MaterialView from '../../../features/materials/ui/MaterialView';
import styles from './MaterialsPage.module.css';

export default function StudentMaterialItemPage() {
  const { id } = useParams();
  return (
    <div className={styles.page}>
      <MaterialView uuid={id} backTo="/student/materials" />
    </div>
  );
}
