import { useParams } from 'react-router-dom';
import MaterialView from '../../../features/materials/ui/MaterialView';
import styles from './PsychologistMaterialsPage.module.css';

export default function PsychologistMaterialItemPage() {
  const { id } = useParams();
  return (
    <div className={styles.page}>
      <MaterialView uuid={id} backTo="/psychologist/materials" />
    </div>
  );
}
