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
        return null; // 401 or anything else => treated as not logged in
      })
      .then((value) => {
        if (active) {
          setUser(value && value.trim() !== '' ? value : null);
        }
      })
      .catch(() => {
        if (active) {
          setUser(null); // network error => treat as anonymous, do NOT redirect
        }
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
