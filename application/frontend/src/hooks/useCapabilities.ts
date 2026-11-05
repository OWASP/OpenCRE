import { useEffect, useState } from 'react';

import { useEnvironment } from './useEnvironment';

export type Capabilities = {
  myopencre: boolean;
  login: boolean;
};

const DEFAULT_CAPABILITIES: Capabilities = {
  myopencre: false,
  login: false,
};

export const useCapabilities = () => {
  const { apiUrl } = useEnvironment();
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const baseUrl = apiUrl.replace('/rest/v1', '');

    fetch(`${baseUrl}/api/capabilities`)
      .then((res) => res.json())
      .then((data: Partial<Capabilities>) =>
        setCapabilities({
          myopencre: Boolean(data?.myopencre),
          login: Boolean(data?.login),
        })
      )
      .catch(() => setCapabilities(DEFAULT_CAPABILITIES))
      .finally(() => setLoading(false));
  }, [apiUrl]);

  return { capabilities, loading };
};
