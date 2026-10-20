/**
 * providers.jsx — React context providers.
 *
 * Add any future global providers (theme, i18n, error boundaries, etc.) here.
 * Keep this file thin: only wrapping, no logic.
 */

import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from '../features/auth/AuthContext';
import { ThemeProvider } from '../features/theme/ThemeContext';
import { A11yProvider } from '../features/a11y/A11yContext';

export default function Providers({ children }) {
  return (
    <ThemeProvider>
      <A11yProvider>
        <BrowserRouter>
          <AuthProvider>
            {children}
          </AuthProvider>
        </BrowserRouter>
      </A11yProvider>
    </ThemeProvider>
  );
}
