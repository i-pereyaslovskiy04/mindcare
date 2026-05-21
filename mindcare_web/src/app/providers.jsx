/**
 * providers.jsx — React context providers.
 *
 * Add any future global providers (theme, i18n, error boundaries, etc.) here.
 * Keep this file thin: only wrapping, no logic.
 */

import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from '../features/auth/AuthContext';

export default function Providers({ children }) {
  return (
    <BrowserRouter>
      <AuthProvider>
        {children}
      </AuthProvider>
    </BrowserRouter>
  );
}
