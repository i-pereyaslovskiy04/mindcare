import '../styles/variables.css';
import '../styles/tokens/coffee-light.css';
import '../styles/tokens/coffee-dark.css';
import '../styles/tokens/nature-light.css';
import '../styles/tokens/nature-dark.css';
import '../styles/tokens/classic-light.css';
import '../styles/tokens/classic-dark.css';
import '../styles/tokens/dongu-light.css';
import '../styles/tokens/dongu-dark.css';
import '../styles/tokens/hc-light.css';
import '../styles/tokens/hc-dark.css';
import '../styles/tokens/hc-rules.css';
import '../styles/tokens/a11y.css';
import '../styles/tokens/base.css';
import '../styles/global.css';
import Providers from './providers';
import AppRouter from './router';
import ImpersonationBanner from '../features/auth/ui/ImpersonationBanner';

export default function App() {
  return (
    <Providers>
      <ImpersonationBanner />
      <AppRouter />
    </Providers>
  );
}
