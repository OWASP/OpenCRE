import { useEffect, useState } from 'react';

import { useEnvironment } from './useEnvironment';

export type ResourceSelectionState = {
  selected: string[];
  loading: boolean;
  saving: boolean;
  error: string | null;
  // True only when the INITIAL load genuinely failed (network / unexpected
  // status) — NOT for the 401 anonymous case. When true the selection is
  // unknown, so callers must not let an empty list overwrite persisted data.
  loadError: boolean;
  save: (next: string[]) => Promise<string[] | null>;
};

// Per-user resource selection (Part of #586). Mirrors useUser's raw-fetch status
// handling: 200 ok, 401 -> anonymous / not available, anything else -> error.
export const useResourceSelection = (): ResourceSelectionState => {
  const { apiUrl } = useEnvironment();
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const res = await fetch(`${apiUrl}/user/resources`, { method: 'GET' });
        if (res.status === 401) {
          return; // anonymous / feature not available — not an error
        }
        if (res.status !== 200) {
          throw new Error(`Unexpected /user/resources status: ${res.status}`);
        }
        const data = await res.json();
        // Only accept a well-formed payload; a malformed 200 must not be treated
        // as an (empty) selection that could later overwrite persisted data.
        if (!data || !Array.isArray(data.selected)) {
          throw new Error('Malformed /user/resources response: missing selected[]');
        }
        if (active) {
          setSelected(data.selected);
        }
      } catch (err) {
        if (active) {
          setError('Could not load your saved standards.');
          setLoadError(true);
        }
        console.error('useResourceSelection: could not load selection', err);
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    load();

    return () => {
      active = false;
    };
  }, [apiUrl]);

  const save = async (next: string[]): Promise<string[] | null> => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${apiUrl}/user/resources`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ selected: next }),
      });
      if (!res.ok) {
        throw new Error(`Unexpected PUT /user/resources status: ${res.status}`);
      }
      const data = await res.json();
      const stored = data && Array.isArray(data.selected) ? data.selected : next;
      setSelected(stored);
      return stored;
    } catch (err) {
      setError('Could not save your standards. Please try again.');
      console.error('useResourceSelection: could not save selection', err);
      return null;
    } finally {
      setSaving(false);
    }
  };

  return { selected, loading, saving, error, loadError, save };
};
