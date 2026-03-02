import { matchPath } from 'react-router';
import { useLocation } from 'react-router-dom';

import { IRoute } from '../routes';

interface UseLocationFromOutsideRouteReturn {
  params: Record<string, string>;
  url: string;
  showFilter: boolean;
}

/**
 * Determines route metadata (params, url, showFilter)
 * based on the currently active route.
 *
 * NOTE:
 * - This hook no longer imports ROUTES directly
 * - Routes must be passed in (already capability-resolved)
 */
export const useLocationFromOutsideRoute = (routes: IRoute[]): UseLocationFromOutsideRouteReturn => {
  const { pathname } = useLocation();

  const currentRoute = routes
    .map(({ path, showFilter }) => ({
      ...matchPath(pathname, {
        path,
        exact: true,
        strict: false,
      }),
      showFilter,
    }))
    .find((matchedPath) => matchedPath?.isExact);

  return {
    params: currentRoute?.params || {},
    url: currentRoute?.url || '',
    showFilter: currentRoute?.showFilter || false,
  };
};
