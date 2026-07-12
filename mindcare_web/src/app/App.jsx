import '../styles/variables.css';
import '../styles/tokens/coffee-light.css';
import '../styles/tokens/base.css';
import '../styles/global.css';
import Providers from './providers';
import AppRouter from './router';

export default function App() {
  return (
    <Providers>
      <AppRouter />
    </Providers>
  );
}
