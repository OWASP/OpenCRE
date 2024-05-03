import { matchPath } from 'react-router';
import { useLocation } from 'react-router-dom';

import { ROUTES } from '../routes';

interface UseLocationFromOutsideRouteReturn {
  params: Record<string, string>;
  url: string;
  showHeaderSearch: boolean;
  showFilter: boolean;
}

export const useLocationFromOutsideRoute = (): UseLocationFromOutsideRouteReturn => {
  // The current URL
  const { pathname } = useLocation();
  // The current ROUTE, from our URL
  const currentRoute = ROUTES.map(({ path, showHeaderSearch, showFilter }) => ({
    ...matchPath(pathname, path),
    showHeaderSearch,
    showFilter,
  })).find((matchedPath) => matchedPath?.isExact);
  return {
    params: currentRoute?.params || {},
    url: currentRoute?.url || '',
    showHeaderSearch: currentRoute?.showHeaderSearch || false,
    showFilter: currentRoute?.showFilter || false,
  };
};
