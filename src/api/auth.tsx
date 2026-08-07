// Real session auth against the backend. The kernel's persona switcher is a
// display convenience layered UNDER this identity — it never substitutes for
// it (Pass 4: personas are not identity).
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { authApi, type Me } from './client';

export type AuthState =
  | { status: 'loading' }
  | { status: 'anon' }
  | { status: 'authed'; me: Me };

interface AuthContextValue {
  state: AuthState;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Convenience: the current user when authenticated, else null. */
  me: Me | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    authApi
      .me()
      .then((me) => !cancelled && setState({ status: 'authed', me }))
      .catch(() => !cancelled && setState({ status: 'anon' }));
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const me = await authApi.login(email, password); // throws ApiError on 401
    setState({ status: 'authed', me });
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout().catch(() => undefined); // server-side revoke is best-effort here
    setState({ status: 'anon' });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ state, login, logout, me: state.status === 'authed' ? state.me : null }),
    [state, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
