import { useEffect, useState } from 'react';

import { useEnvironment } from './useEnvironment';

export type UserState = {
  user: string | null;
  isLoggedIn: boolean;
  loading: boolean;
};

export const useUser = () => {
  const { apiUrl } = useEnvironment();
  const [user, setUser] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    fetch(`${apiUrl}/user`, { method: 'GET' })
      .then((res) => {
        if (res.status === 200) {
          return res.text();
        }
        if (res.status === 401) {
          return null; // the normal anonymous case — not logged in
        }
        // Unexpected status (e.g. 5xx): a real failure, not a clean anonymous state.
        throw new Error(`Unexpected /user status: ${res.status}`);
      })
      .then((value) => {
        if (active) {
          setUser(value && value.trim() !== '' ? value : null);
        }
      })
      .catch((err) => {
        // Network error or unexpected status. Degrade to anonymous so public
        // pages stay accessible (never block or redirect), but log the failure
        // instead of silently masking it as a normal logged-out state.
        if (active) {
          setUser(null);
        }
        console.error('useUser: could not resolve /user login state', err);
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [apiUrl]);

  const login = () => {
    window.location.href = `${apiUrl}/login`;
  };

  const logout = () => {
    window.location.href = `${apiUrl}/logout`;
  };

  return { user, isLoggedIn: user !== null, loading, login, logout };
};
